package main

import (
	"bufio"
	"bytes"
	"database/sql"
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/go-sql-driver/mysql"
	_ "github.com/go-sql-driver/mysql"
)

type MySQLInserter struct {
	db     *sql.DB
	params ConnParams
}

func NewMySQLInserter(params ConnParams) (*MySQLInserter, error) {
	dsn := fmt.Sprintf(
		"%s:%s@tcp(%s:%d)/%s",
		params.User, params.Password, params.Host, params.Port, params.Database,
	)
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping: %w", err)
	}
	return &MySQLInserter{db: db, params: params}, nil
}

func (ins *MySQLInserter) Close() {
	ins.db.Close()
}

func (ins *MySQLInserter) CountRows(tableName string) (int, error) {
	var n int
	err := ins.db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", ins.quote(tableName))).Scan(&n)
	if err != nil {
		return 0, fmt.Errorf("count rows: %w", err)
	}
	return n, nil
}

func (ins *MySQLInserter) quote(name string) string {
	clean := cleanStr(name)
	return "`" + strings.ReplaceAll(clean, "`", "``") + "`"
}

func (ins *MySQLInserter) placeholder(_ int) string {
	return "?"
}

func (ins *MySQLInserter) DefaultInsert(csvFile, tableName string) (int, error) {
	stream, err := openCSV(csvFile)
	if err != nil {
		return 0, err
	}
	defer stream.Close()

	cols := make([]string, len(stream.Headers))
	phs  := make([]string, len(stream.Headers))
	for i, h := range stream.Headers {
		cols[i] = ins.quote(h)
		phs[i]  = "?"
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

func (ins *MySQLInserter) BulkInsert(csvFile, tableName string, batchSize int) (int, error) {
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

	// Заранее построим шаблон одной группы (?, ?, ?...).
	rowPhs := "(" + strings.Repeat("?, ", ncols-1) + "?)"

	batch := make([][]string, 0, batchSize)

	flushBatch := func() error {
		if len(batch) == 0 {
			return nil
		}
		valueStrings := make([]string, len(batch))
		valueArgs    := make([]interface{}, 0, len(batch)*ncols)
		for j, row := range batch {
			valueStrings[j] = rowPhs
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

func (ins *MySQLInserter) FileInsert(csvFile, tableName string) (int, error) {
	// Парсить CSV в Go не нужно — сервер MySQL сам читает файл через
	// LOAD DATA LOCAL INFILE. Возвращаемое значение метода больше не
	// используется в main: фактическое число строк подсчитывается через
	// CountRows() уже после замера времени.
	absPath, err := toAbsPath(csvFile)
	if err != nil {
		return 0, err
	}
	mysql.RegisterLocalFile(absPath)

	lineTerm, err := detectLinesTerminator(csvFile)
	if err != nil {
		return 0, err
	}

	query := fmt.Sprintf(`
		LOAD DATA LOCAL INFILE '%s'
		INTO TABLE %s
		FIELDS TERMINATED BY ','
		OPTIONALLY ENCLOSED BY '"'
		LINES TERMINATED BY '%s'
		IGNORE 1 ROWS
	`, absPath, ins.quote(tableName), lineTerm)

	if _, err := ins.db.Exec(query); err != nil {
		return 0, fmt.Errorf("load data infile: %w", err)
	}
	return 0, nil
}

// detectLinesTerminator определяет line-ending CSV-файла без декодирования.
// Возвращает строку-аргумент для LOAD DATA LINES TERMINATED BY: `\r\n` или `\n`.
// MySQL LOAD DATA INFILE строгий: при несовпадении весь файл воспринимается
// как одна «строка», и IGNORE 1 ROWS оставляет 1 битую запись.
func detectLinesTerminator(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("detect line endings: %w", err)
	}
	defer f.Close()
	buf := make([]byte, 8192)
	n, _ := f.Read(buf)
	if bytes.Contains(buf[:n], []byte("\r\n")) {
		return `\r\n`, nil
	}
	return `\n`, nil
}

// toAbsPath возвращает абсолютный путь к файлу в форме, пригодной для:
//   1) mysql.RegisterLocalFile — реестр путей, разрешённых для LOAD DATA LOCAL;
//   2) подстановки в SQL-строку `LOAD DATA LOCAL INFILE '...'`.
//
// Заменяем все `\` на `/`: на Windows MySQL-парсер по умолчанию интерпретирует
// `\\`, `\U`, `\t` и т.д. как escape-последовательности и портит путь.
// Forward slashes одинаково корректны и в Windows API, и в MySQL.
func toAbsPath(path string) (string, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	return strings.ReplaceAll(abs, `\`, "/"), nil
}

func rowToArgs(row []string) []interface{} {
	args := make([]interface{}, len(row))
	for i, v := range row {
		args[i] = v
	}
	return args
}

func cleanStr(s string) string {
	for {
		stripped := strings.TrimSpace(s)
		stripped  = strings.Trim(stripped, `"`)
		stripped  = strings.Trim(stripped, "`")
		stripped  = strings.Trim(stripped, `'`)
		stripped  = strings.TrimSpace(stripped)
		if stripped == s {
			break
		}
		s = stripped
	}
	return s
}

// CSVStream — потоковый CSV-ридер. В отличие от старого readCSV (грузил всё
// в [][]string и упирался в RAM на 10⁷ строк) — читает по одной строке при
// каждом вызове Next().
//
// Использование:
//
//	stream, err := openCSV(path)
//	if err != nil { ... }
//	defer stream.Close()
//	for {
//	    row, ok, err := stream.Next()
//	    if err != nil { ... }
//	    if !ok { break }
//	    ... // обработать row
//	}
type CSVStream struct {
	Headers []string

	file    *os.File
	scanner *bufio.Scanner
}

func openCSV(path string) (*CSVStream, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open: %w", err)
	}

	scanner := bufio.NewScanner(f)
	// Большой буфер: одна строка CSV в широких таблицах может быть длинной.
	scanner.Buffer(make([]byte, 1024*1024), 16*1024*1024)

	if !scanner.Scan() {
		f.Close()
		if err := scanner.Err(); err != nil {
			return nil, fmt.Errorf("scan header: %w", err)
		}
		return nil, fmt.Errorf("csv is empty")
	}
	headerLine := scanner.Text()
	headers, err := parseWrappedLine(headerLine)
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("parse headers: %w", err)
	}
	if len(headers) > 0 {
		headers[0] = strings.TrimPrefix(headers[0], "\xef\xbb\xbf")
	}

	return &CSVStream{
		Headers: headers,
		file:    f,
		scanner: scanner,
	}, nil
}

// Next возвращает следующую непустую строку CSV.
// ok=false при достижении EOF.
func (s *CSVStream) Next() (row []string, ok bool, err error) {
	for s.scanner.Scan() {
		line := s.scanner.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		row, err = parseWrappedLine(line)
		if err != nil {
			return nil, false, fmt.Errorf("parse row: %w", err)
		}
		return row, true, nil
	}
	if err := s.scanner.Err(); err != nil {
		return nil, false, fmt.Errorf("scan: %w", err)
	}
	return nil, false, nil
}

func (s *CSVStream) Close() error {
	return s.file.Close()
}

// countCsvDataRows — потоковый счётчик строк данных (всего непустых минус
// заголовок). Не парсит CSV, не загружает файл в память.
//
// Нужен для file_insert: MySQL-драйвер на LOAD DATA INFILE возвращает в
// RowsAffected() единицу (статус OK-пакета), а не число загруженных строк.
// Поэтому считаем строки сами одним проходом по файлу.
func countCsvDataRows(path string) (int, error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, fmt.Errorf("count open: %w", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1024*1024), 16*1024*1024)

	total := 0
	for scanner.Scan() {
		if strings.TrimSpace(scanner.Text()) == "" {
			continue
		}
		total++
	}
	if err := scanner.Err(); err != nil {
		return 0, fmt.Errorf("count scan: %w", err)
	}

	if total > 0 {
		return total - 1, nil // минус заголовок
	}
	return 0, nil
}

func parseWrappedLine(line string) ([]string, error) {
	s := strings.TrimSpace(line)
	if len(s) >= 2 && s[0] == '"' && s[len(s)-1] == '"' {
		s = s[1 : len(s)-1]
	}
	normalized := strings.ReplaceAll(s, `""`, `"`)

	reader                 := csv.NewReader(strings.NewReader(normalized))
	reader.LazyQuotes       = true
	reader.TrimLeadingSpace = true

	fields, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("csv parse %q: %w", normalized, err)
	}
	for i, f := range fields {
		fields[i] = cleanStr(f)
	}
	return fields, nil
}

type ConnParams struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
}