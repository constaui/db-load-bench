use crate::csv::{csv_read, clean_identifier};
use crate::inserter::{ConnParams, Inserter};
use anyhow::{Result, anyhow};
use postgres::{Client, NoTls};
use std::fmt::Write;

pub struct PgSQLInserter {
    client: Client,
}

impl PgSQLInserter {
    pub fn new(p: &ConnParams) -> Result<Self> {
        let dsn = format!(
            "host={} port={} user={} password={} dbname={} sslmode=disable",
            p.host, p.port, p.user, p.password, p.database
        );
        let client = Client::connect(&dsn, NoTls)?;
        Ok(Self { client })
    }

    fn quote(name: &str) -> String {
        let clean = clean_identifier(name);
        format!("\"{}\"", clean.replace('"', "\"\""))
    }

    fn build_cols(headers: &[String]) -> String {
        headers.iter()
            .map(|h| Self::quote(h))
            .collect::<Vec<_>>()
            .join(", ")
    }

    fn build_placeholders(count: usize) -> String {
        (1..=count)
            .map(|i| format!("${}", i))
            .collect::<Vec<_>>()
            .join(", ")
    }

    fn escape_csv_field(val: &str) -> String {
        if val.contains(',') || val.contains('"') || val.contains('\n') {
            format!("\"{}\"", val.replace('"', "\"\""))
        } else {
            val.to_string()
        }
    }
}

impl Inserter for PgSQLInserter {

    fn default_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        let data  = csv_read(csv_file)?;
        let ncols = data.headers.len();
        let sql   = format!(
            "INSERT INTO {} ({}) VALUES ({})",
            Self::quote(table),
            Self::build_cols(&data.headers),
            Self::build_placeholders(ncols),
        );

        let stmt = self.client.prepare(&sql)?;

        let mut tx = self.client.transaction()?;
        for row in &data.rows {
            let params: Vec<&(dyn postgres::types::ToSql + Sync)> = row.iter()
                .map(|v| v as &(dyn postgres::types::ToSql + Sync))
                .collect();
            tx.execute(&stmt, &params)?;
        }
        tx.commit()?;
        Ok(data.rows.len())
    }

    fn bulk_insert(&mut self, csv_file: &str, table: &str,
                   batch_size: usize) -> Result<usize> {
        let data   = csv_read(csv_file)?;
        let ncols  = data.headers.len();
        let cols   = Self::build_cols(&data.headers);
        let qtable = Self::quote(table);
        let mut total = 0;

        for chunk in data.rows.chunks(batch_size) {
            let mut sql = format!("INSERT INTO {} ({}) VALUES ", qtable, cols);
            let mut param_idx = 1;

            for (r, _) in chunk.iter().enumerate() {
                if r > 0 { sql.push_str(", "); }
                sql.push('(');
                for c in 0..ncols {
                    if c > 0 { sql.push_str(", "); }
                    write!(sql, "${}", param_idx).unwrap();
                    param_idx += 1;
                }
                sql.push(')');
            }

            let params: Vec<&(dyn postgres::types::ToSql + Sync)> = chunk.iter()
                .flat_map(|row| row.iter()
                    .map(|v| v as &(dyn postgres::types::ToSql + Sync)))
                .collect();

            let mut tx = self.client.transaction()?;
            tx.execute(sql.as_str(), &params)?;
            tx.commit()?;
            total += chunk.len();
        }

        Ok(total)
    }

    fn file_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        let content = std::fs::read_to_string(csv_file)?;
        let row_count = content.lines().count().saturating_sub(1);

        let copy_sql = format!(
            "COPY {} FROM STDIN WITH (FORMAT csv, HEADER true)",
            Self::quote(table)
        );

        let mut writer = self.client
            .copy_in(&copy_sql)
            .map_err(|e| anyhow!("COPY error: {}", e))?;

        let mut file = std::fs::File::open(csv_file)
            .map_err(|e| anyhow!("open file: {}", e))?;
        std::io::copy(&mut file, &mut writer)
            .map_err(|e| anyhow!("COPY write error: {}", e))?;

        writer.finish()
            .map_err(|e| anyhow!("COPY finish error: {}", e))?;

        Ok(row_count)
    }
}