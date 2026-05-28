package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"
)

type Result struct {
	Engine           string                 `json:"engine"`
	DbType           string                 `json:"db_type"`
	Method           string                 `json:"method"`
	ExperimentConfig map[string]int         `json:"experiment_config"`
	MethodConfig     map[string]interface{} `json:"method_config"`
	Metrics          map[string]float64     `json:"metrics"`
}

type Inserter interface {
	DefaultInsert(csvFile, tableName string) (int, error)
	BulkInsert(csvFile, tableName string, batchSize int) (int, error)
	FileInsert(csvFile, tableName string) (int, error)
	// CountRows возвращает фактическое число строк в таблице,
	// запрашивая SELECT COUNT(*) — независимая проверка результата
	// вставки, не зависящая от драйвера/счётчика итераций.
	CountRows(tableName string) (int, error)
	Close()
}

func main() {
	method    := flag.String("method",     "default_insert", "Insert method")
	csvFile   := flag.String("csv",        "",               "Path to CSV file")
	tableName := flag.String("table",      "Test",           "Table name")
	dbType    := flag.String("db-type",    "mysql",          "Database type: mysql | postgresql")
	host      := flag.String("host",       "localhost",      "Database host")
	port      := flag.Int("port",          3306,             "Database port")
	user      := flag.String("user",       "",               "Database user")
	password  := flag.String("password",   "",               "Database password")
	database  := flag.String("database",   "",               "Database name")
	batchSize := flag.Int("batch-size",    1000,             "Batch size for bulk_insert")
	flag.Parse()

	if *csvFile == "" {
		fmt.Fprintln(os.Stderr, "error: --csv is required")
		os.Exit(1)
	}

	params := ConnParams{
		Host:     *host,
		Port:     *port,
		User:     *user,
		Password: *password,
		Database: *database,
	}

	var inserter Inserter
	var err     error

	switch *dbType {
	case "mysql":
		inserter, err = NewMySQLInserter(params)
	case "postgresql":
		inserter, err = NewPgSQLInserter(params)
	default:
		fmt.Fprintf(os.Stderr, "unsupported db type: %s\n", *dbType)
		os.Exit(1)
	}

	if err != nil {
		fmt.Fprintln(os.Stderr, "connection error:", err)
		os.Exit(1)
	}
	defer inserter.Close()

	start := time.Now()

	switch *method {
	case "default_insert":
		_, err = inserter.DefaultInsert(*csvFile, *tableName)
	case "bulk_insert":
		_, err = inserter.BulkInsert(*csvFile, *tableName, *batchSize)
	case "file_insert":
		_, err = inserter.FileInsert(*csvFile, *tableName)
	default:
		fmt.Fprintf(os.Stderr, "unknown method: %s\n", *method)
		os.Exit(1)
	}

	elapsed := time.Since(start).Seconds()

	if err != nil {
		fmt.Fprintln(os.Stderr, "insert error:", err)
		os.Exit(1)
	}

	// Число вставленных строк берём из самой БД — независимая проверка
	// результата (не файл, не счётчик драйвера, не счётчик итераций).
	rows, err := inserter.CountRows(*tableName)
	if err != nil {
		fmt.Fprintln(os.Stderr, "count rows error:", err)
		os.Exit(1)
	}

	var batchSizeVal interface{}
	if *method == "bulk_insert" {
		batchSizeVal = *batchSize
	}

	result := Result{
		Engine: "Go",
		DbType: *dbType,
		Method: *method,
		ExperimentConfig: map[string]int{
			"rows": rows,
		},
		MethodConfig: map[string]interface{}{
			"batch_size": batchSizeVal,
		},
		Metrics: map[string]float64{
			"elapsed": elapsed,
			"rps":     float64(rows) / elapsed,
		},
	}

	out, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintln(os.Stderr, "json marshal error:", err)
		os.Exit(1)
	}

	fmt.Println(string(out))
}