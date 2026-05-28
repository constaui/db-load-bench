package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"strings"

	"github.com/jackc/pgx/v5"
	_ "github.com/jackc/pgx/v5/stdlib"
)

type PgSQLInserter struct {
	db     *sql.DB
	params ConnParams
}

func NewPgSQLInserter(params ConnParams) (*PgSQLInserter, error) {
	dsn := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		params.Host, params.Port, params.User, params.Password, params.Database,
	)
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping: %w", err)
	}
	return &PgSQLInserter{db: db, params: params}, nil
}

func (ins *PgSQLInserter) Close() {
	ins.db.Close()
}

func (ins *PgSQLInserter) CountRows(tableName string) (int, error) {
	var n int
	err := ins.db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", ins.quote(tableName))).Scan(&n)
	if err != nil {
		return 0, fmt.Errorf("count rows: %w", err)
	}
	return n, nil
}

func (ins *PgSQLInserter) quote(name string) string {
	clean := cleanStr(name)
	return `"` + strings.ReplaceAll(clean, `"`, `""`) + `"`
}

func (ins *PgSQLInserter) placeholder(i int) string {
	return fmt.Sprintf("$%d", i+1)
}

func (ins *PgSQLInserter) DefaultInsert(csvFile, tableName string) (int, error) {
	stream, err := openCSV(csvFile)
	if err != nil {
		return 0, err
	}
	defer stream.Close()

	cols := make([]string, len(stream.Headers))
	phs  := make([]string, len(stream.Headers))
	for i, h := range stream.Headers {
		cols[i] = ins.quote(h)
		phs[i]  = ins.placeholder(i)
	}

	query := fmt.Sprintf(
		"INSERT INTO %s (%s) VALUES (%s)",
		ins.quote(tableName),
		strings.Join(cols, ", "),
		strings.Join(phs, ", "),
	)

	tx, err := ins.db.Begin()
	if err != nil {
		return 0, fmt.Errorf("begin tx: %w", err)
	}
	stmt, err := tx.Prepare(query)
	if err != nil {
		tx.Rollback()
		return 0, fmt.Errorf("prepare stmt: %w", err)
	}
	defer stmt.Close()

	count := 0
	for {
		row, ok, err := stream.Next()
		if err != nil {
			tx.Rollback()
			return 0, err
		}
		if !ok {
			break
		}
		if _, err := stmt.Exec(rowToArgs(row)...); err != nil {
			tx.Rollback()
			return 0, fmt.Errorf("exec row: %w", err)
		}
		count++
	}

	return count, tx.Commit()
}

func (ins *PgSQLInserter) BulkInsert(csvFile, tableName string, batchSize int) (int, error) {
	stream, err := openCSV(csvFile)
	if err != nil {
		return 0, err
	}
	defer stream.Close()

	cols := make([]string, len(stream.Headers))
	for i, h := range stream.Headers {
		cols[i] = ins.quote(h)
	}
	colStr := strings.Join(cols, ", ")
	table  := ins.quote(tableName)
	ncols  := len(stream.Headers)
	total  := 0

	batch := make([][]string, 0, batchSize)

	flushBatch := func() error {
		if len(batch) == 0 {
			return nil
		}
		// PostgreSQL использует $N плейсхолдеры с глобальной нумерацией —
		// строим её на лету для каждой пачки.
		valueStrings := make([]string, len(batch))
		valueArgs    := make([]interface{}, 0, len(batch)*ncols)
		for j, row := range batch {
			phs := make([]string, ncols)
			for k := 0; k < ncols; k++ {
				phs[k] = ins.placeholder(j*ncols + k)
			}
			valueStrings[j] = "(" + strings.Join(phs, ", ") + ")"
			valueArgs = append(valueArgs, rowToArgs(row)...)
		}
		query := fmt.Sprintf(
			"INSERT INTO %s (%s) VALUES %s",
			table, colStr, strings.Join(valueStrings, ", "),
		)
		tx, err := ins.db.Begin()
		if err != nil {
			return fmt.Errorf("begin tx: %w", err)
		}
		if _, err := tx.Exec(query, valueArgs...); err != nil {
			tx.Rollback()
			return fmt.Errorf("exec batch: %w", err)
		}
		if err := tx.Commit(); err != nil {
			return fmt.Errorf("commit: %w", err)
		}
		total += len(batch)
		batch = batch[:0]
		return nil
	}

	for {
		row, ok, err := stream.Next()
		if err != nil {
			return total, err
		}
		if !ok {
			break
		}
		batch = append(batch, row)
		if len(batch) >= batchSize {
			if err := flushBatch(); err != nil {
				return total, err
			}
		}
	}
	if err := flushBatch(); err != nil {
		return total, err
	}

	return total, nil
}

func (ins *PgSQLInserter) FileInsert(csvFile, tableName string) (int, error) {
	// Файл не парсим в Go вообще — стримим напрямую через COPY FROM STDIN.
	// PostgreSQL сам понимает CSV (RFC 4180). RowsAffected возвращает
	// фактическое число вставленных строк.
	ctx := context.Background()
	dsn := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		ins.params.Host, ins.params.Port,
		ins.params.User, ins.params.Password, ins.params.Database,
	)
	conn, err := pgx.Connect(ctx, dsn)
	if err != nil {
		return 0, fmt.Errorf("pgx connect: %w", err)
	}
	defer conn.Close(ctx)

	f, err := os.Open(csvFile)
	if err != nil {
		return 0, fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	copySQL := fmt.Sprintf(
		"COPY %s FROM STDIN WITH (FORMAT csv, HEADER true)",
		ins.quote(tableName),
	)

	tag, err := conn.PgConn().CopyFrom(ctx, f, copySQL)
	if err != nil {
		return 0, fmt.Errorf("copy from stdin: %w", err)
	}
	return int(tag.RowsAffected()), nil
}