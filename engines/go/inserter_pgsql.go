package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"fmt"
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

func (ins *PgSQLInserter) quote(name string) string {
	clean := cleanStr(name)
	return `"` + strings.ReplaceAll(clean, `"`, `""`) + `"`
}

func (ins *PgSQLInserter) placeholder(i int) string {
	return fmt.Sprintf("$%d", i+1)
}

func (ins *PgSQLInserter) DefaultInsert(csvFile, tableName string) (int, error) {
	data, err := readCSV(csvFile)
	if err != nil {
		return 0, err
	}

	cols := make([]string, len(data.Headers))
	phs  := make([]string, len(data.Headers))
	for i, h := range data.Headers {
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

	for _, row := range data.Rows {
		if _, err := stmt.Exec(rowToArgs(row)...); err != nil {
			tx.Rollback()
			return 0, fmt.Errorf("exec row: %w", err)
		}
	}

	return len(data.Rows), tx.Commit()
}

func (ins *PgSQLInserter) BulkInsert(csvFile, tableName string, batchSize int) (int, error) {
	data, err := readCSV(csvFile)
	if err != nil {
		return 0, err
	}

	cols := make([]string, len(data.Headers))
	for i, h := range data.Headers {
		cols[i] = ins.quote(h)
	}
	colStr := strings.Join(cols, ", ")
	table  := ins.quote(tableName)
	total  := 0

	for i := 0; i < len(data.Rows); i += batchSize {
		end := i + batchSize
		if end > len(data.Rows) {
			end = len(data.Rows)
		}
		batch := data.Rows[i:end]

		valueStrings := make([]string, len(batch))
		valueArgs    := make([]interface{}, 0, len(batch)*len(data.Headers))

		for j, row := range batch {
			phs := make([]string, len(data.Headers))
			for k := range data.Headers {
				phs[k] = ins.placeholder(j*len(data.Headers) + k)
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
			return total, fmt.Errorf("begin tx: %w", err)
		}
		if _, err := tx.Exec(query, valueArgs...); err != nil {
			tx.Rollback()
			return total, fmt.Errorf("exec batch: %w", err)
		}
		if err := tx.Commit(); err != nil {
			return total, fmt.Errorf("commit: %w", err)
		}
		total += len(batch)
	}

	return total, nil
}

func (ins *PgSQLInserter) FileInsert(csvFile, tableName string) (int, error) {
	data, err := readCSV(csvFile)
	if err != nil {
		return 0, err
	}

	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)

	cleanHeaders := make([]string, len(data.Headers))
	for i, h := range data.Headers {
		cleanHeaders[i] = cleanStr(h)
	}
	writer.Write(cleanHeaders)
	writer.WriteAll(data.Rows)
	writer.Flush()

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

	copySQL := fmt.Sprintf(
		"COPY %s FROM STDIN WITH (FORMAT csv, HEADER true)",
		ins.quote(tableName),
	)

	tag, err := conn.PgConn().CopyFrom(ctx, &buf, copySQL)
	if err != nil {
		return 0, fmt.Errorf("copy from stdin: %w", err)
	}

	return int(tag.RowsAffected()), nil
}