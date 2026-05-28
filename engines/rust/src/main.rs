mod csv;
mod inserter;
mod inserter_mysql;
mod inserter_pgsql;

#[cfg(test)]
mod csv_tests;

use inserter::{ConnParams, Inserter};
use inserter_mysql::MySQLInserter;
use inserter_pgsql::PgSQLInserter;
use std::time::Instant;

fn get_arg<'a>(args: &'a [String], key: &str, default: &'a str) -> &'a str {
    args.windows(2)
        .find(|w| w[0] == key)
        .map(|w| w[1].as_str())
        .unwrap_or(default)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    let method    = get_arg(&args, "--method",     "default_insert");
    let csv_file  = get_arg(&args, "--csv",        "");
    let table     = get_arg(&args, "--table",      "Test");
    let db_type   = get_arg(&args, "--db-type",    "mysql");
    let host      = get_arg(&args, "--host",       "localhost");
    let port      = get_arg(&args, "--port",       "3306");
    let user      = get_arg(&args, "--user",       "");
    let password  = get_arg(&args, "--password",   "");
    let database  = get_arg(&args, "--database",   "");
    let batch_str = get_arg(&args, "--batch-size", "1000");

    if csv_file.is_empty() {
        eprintln!("error: --csv is required");
        std::process::exit(1);
    }

    let params = ConnParams {
        host:     host.to_string(),
        port:     port.parse().unwrap_or(3306),
        user:     user.to_string(),
        password: password.to_string(),
        database: database.to_string(),
    };

    let mut ins: Box<dyn Inserter> = match db_type {
        "mysql" => match MySQLInserter::new(&params) {
            Ok(i)  => Box::new(i),
            Err(e) => { eprintln!("connection error: {}", e); std::process::exit(1); }
        },
        "postgresql" => match PgSQLInserter::new(&params) {
            Ok(i)  => Box::new(i),
            Err(e) => { eprintln!("connection error: {}", e); std::process::exit(1); }
        },
        _ => { eprintln!("unsupported db type: {}", db_type); std::process::exit(1); }
    };

    let batch_size: usize = batch_str.parse().unwrap_or(1000);
    let start = Instant::now();

    let rows = match method {
        "default_insert" => ins.default_insert(csv_file, table),
        "bulk_insert"    => ins.bulk_insert(csv_file, table, batch_size),
        "file_insert"    => ins.file_insert(csv_file, table),
        _ => { eprintln!("unknown method: {}", method); std::process::exit(1); }
    };

    let rows = match rows {
        Ok(r)  => r,
        Err(e) => { eprintln!("insert error: {}", e); std::process::exit(1); }
    };

    let elapsed = start.elapsed().as_secs_f64();
    let is_bulk = method == "bulk_insert";

    println!(
        "{{\"engine\":\"Rust\",\"db_type\":\"{}\",\"method\":\"{}\",\
         \"experiment_config\":{{\"rows\":{}}},\
         \"method_config\":{{\"batch_size\":{}}},\
         \"metrics\":{{\"elapsed\":{:.6},\"rps\":{:.1}}}}}",
        db_type, method, rows,
        if is_bulk { batch_str.to_string() } else { "null".to_string() },
        elapsed,
        rows as f64 / elapsed
    );
}