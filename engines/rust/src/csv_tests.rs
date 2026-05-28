#[cfg(test)]
mod tests {
    use crate::csv::CsvStream;
    use std::io::Write;

    fn write_tmp(slot: &str, content: &str) -> std::path::PathBuf {
        let mut path = std::env::temp_dir();
        path.push(format!("csvstream_{}_{}.csv", std::process::id(), slot));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(content.as_bytes()).unwrap();
        path
    }

    #[test]
    fn reads_headers_and_rows() {
        let path = write_tmp(
            "headers",
            "id,name,email\n1,Alice,a@x.com\n2,Bob,b@x.com\n3,\"Charlie, Jr\",c@x.com\n",
        );
        let mut stream = CsvStream::open(path.to_str().unwrap()).unwrap();

        assert_eq!(stream.headers, vec!["id", "name", "email"]);

        let mut rows: Vec<Vec<String>> = Vec::new();
        for row in stream.by_ref() {
            rows.push(row.unwrap());
        }
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[2], vec!["3", "Charlie, Jr", "c@x.com"]);

        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn skips_blank_lines() {
        let path = write_tmp("blanks", "a,b\n1,2\n\n3,4\n");
        let mut stream = CsvStream::open(path.to_str().unwrap()).unwrap();
        let count = stream.by_ref().count();
        assert_eq!(count, 2);
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn empty_file_errs() {
        let path = write_tmp("empty", "");
        assert!(CsvStream::open(path.to_str().unwrap()).is_err());
        std::fs::remove_file(&path).ok();
    }
}
