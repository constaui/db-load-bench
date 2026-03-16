package main

import (
	"bufio"
	"database/sql"
	"encoding/csv"
	"fmt"
	"os"
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

func (ins *MySQLInserter) quote(name string) string {
	clean := cleanStr(name)
	return "`" + strings.ReplaceAll(clean, "`", "``") + "`"
}

func (ins *MySQLInserter) placeholder(_ int) string {
	return "?"
}

func (ins *MySQLInserter) DefaultInsert(csvFile, tableName string) (int, error) {
	data, err := readCSV(csvFile)
	if err != nil {
		return 0, err
	}

	cols := make([]string, len(data.Headers))
	phs  := make([]string, len(data.Headers))
	for i, h := range data.Headers {
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

	for _, row := range data.Rows {
		if _, err := stmt.Exec(rowToArgs(row)...); err != nil {
			tx.Rollback()
			return 0, fmt.Errorf("exec row: %w", err)
		}
	}

	return len(data.Rows), tx.Commit()
}

func (ins *MySQLInserter) BulkInsert(csvFile, tableName string, batchSize int) (int, error) {
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
				phs[k] = "?"
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

func (ins *MySQLInserter) FileInsert(csvFile, tableName string) (int, error) {
	data, err := readCSV(csvFile)
	if err != nil {
		return 0, err
	}
	rowCount := len(data.Rows)

	absPath, err := toAbsPath(csvFile)
	if err != nil {
		return 0, err
	}
	mysql.RegisterLocalFile(absPath)

	query := fmt.Sprintf(`
		LOAD DATA LOCAL INFILE '%s'
		INTO TABLE %s
		FIELDS TERMINATED BY ','
		OPTIONALLY ENCLOSED BY '"'
		LINES TERMINATED BY '\n'
		IGNORE 1 ROWS
	`, absPath, ins.quote(tableName))

	if _, err := ins.db.Exec(query); err != nil {
		return 0, fmt.Errorf("load data infile: %w", err)
	}

	return rowCount, nil
}

func toAbsPath(path string) (string, error) {
	if strings.HasPrefix(path, "/") {
		return path, nil
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	return wd + "/" + path, nil
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

func readCSV(path string) (*CSVData, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open: %w", err)
	}
	defer f.Close()

	var lines []string
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("scan: %w", err)
	}
	if len(lines) == 0 {
		return nil, fmt.Errorf("csv is empty")
	}

	headers, err := parseWrappedLine(lines[0])
	if err != nil {
		return nil, fmt.Errorf("parse headers: %w", err)
	}
	if len(headers) > 0 {
		headers[0] = strings.TrimPrefix(headers[0], "\xef\xbb\xbf")
	}

	var rows [][]string
	for i, line := range lines[1:] {
		if strings.TrimSpace(line) == "" {
			continue
		}
		row, err := parseWrappedLine(line)
		if err != nil {
			return nil, fmt.Errorf("parse row %d: %w", i+1, err)
		}
		rows = append(rows, row)
	}

	return &CSVData{Headers: headers, Rows: rows}, nil
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

type CSVData struct {
	Headers []string
	Rows    [][]string
}

type ConnParams struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
}