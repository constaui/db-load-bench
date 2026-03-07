package main

import (
	"database/sql"
	"fmt"

	_ "github.com/go-sql-driver/mysql"
	_ "github.com/jackc/pgx/v5/stdlib"
)

func newSQLDB(dbType, host string, port int, user, password, database string) (*sql.DB, error) {
	driver, dsn, err := buildDSN(dbType, host, port, user, password, database)
	if err != nil {
		return nil, err
	}

	db, err := sql.Open(driver, dsn)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}

	

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping: %w", err)
	}

	return db, nil
}

func buildDSN(dbType, host string, port int, user, password, database string) (string, string, error) {
	switch dbType {
	case "mysql":
		dsn := fmt.Sprintf(
			"%s:%s@tcp(%s:%d)/%s?allowLocalInfile=true",
			user, password, host, port, database,
		)
		return "mysql", dsn, nil

	case "postgresql":
		dsn := fmt.Sprintf(
			"host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
			host, port, user, password, database,
		)
		return "pgx", dsn, nil  // "pgx" — имя драйвера pgx/v5/stdlib

	default:
		return "", "", fmt.Errorf("unsupported db type: %s", dbType)
	}
}