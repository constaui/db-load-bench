import org.postgresql.copy.CopyManager;
import org.postgresql.core.BaseConnection;

import java.io.*;
import java.sql.*;
import java.util.*;

public class InserterPgSQL implements Inserter {

    private final Connection conn;
    private final ConnParams params;

    public InserterPgSQL(ConnParams p) throws SQLException {
        try {
            Class.forName("org.postgresql.Driver");
        } catch (ClassNotFoundException e) {
            throw new SQLException("PostgreSQL driver not found", e);
        }
        
        String url = String.format(
            "jdbc:postgresql://%s:%d/%s?sslmode=disable",
            p.host, p.port, p.database
        );
        Properties props = new Properties();
        props.setProperty("user",     p.user);
        props.setProperty("password", p.password);

        conn         = DriverManager.getConnection(url, props);
        this.params  = p;
    }

    @Override
    public void close() {
        try { if (conn != null) conn.close(); }
        catch (SQLException ignored) {}
    }

    private String quote(String name) {
        String clean = CSVReader.cleanIdentifier(name)
                                .replace("\"", "\"\"");
        return "\"" + clean + "\"";
    }

    private String placeholder(int i) {
        return "?";
    }

    @Override
    public int defaultInsert(String csvFile, String tableName) throws Exception {
        int total = 0;
        conn.setAutoCommit(false);
        try (CSVStream csv = new CSVStream(csvFile)) {
            String cols = buildCols(csv.headers);
            String phs  = buildPlaceholders(csv.headers.size());
            String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                        quote(tableName), cols, phs);

            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                while (csv.hasNext()) {
                    String[] row = csv.next();
                    for (int i = 0; i < row.length; i++) {
                        ps.setString(i + 1, row[i]);
                    }
                    ps.executeUpdate();
                    total++;
                }
                conn.commit();
            }
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }
        return total;
    }

    @Override
    public int bulkInsert(String csvFile, String tableName, int batchSize) throws Exception {
        int total = 0;
        conn.setAutoCommit(false);
        try (CSVStream csv = new CSVStream(csvFile)) {
            String cols = buildCols(csv.headers);
            String phs  = buildPlaceholders(csv.headers.size());
            String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                        quote(tableName), cols, phs);

            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                int count = 0;
                while (csv.hasNext()) {
                    String[] row = csv.next();
                    for (int i = 0; i < row.length; i++) {
                        ps.setString(i + 1, row[i]);
                    }
                    ps.addBatch();
                    count++;

                    if (count >= batchSize) {
                        ps.executeBatch();
                        total += count;
                        count = 0;
                    }
                }
                if (count > 0) {
                    ps.executeBatch();
                    total += count;
                }
                conn.commit();
            }
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }
        return total;
    }

    @Override
    public int fileInsert(String csvFile, String tableName) throws Exception {
        // Стримим файл напрямую в PostgreSQL COPY, без парсинга в Java.
        // Парсинг и StringBuilder-копия съедали ~2× размер файла в куче и
        // приводили к OutOfMemoryError на больших объёмах (10⁷ строк).
        // PostgreSQL COPY понимает RFC 4180 CSV сам.
        String copySQL = String.format(
            "COPY %s FROM STDIN WITH (FORMAT csv, HEADER true)",
            quote(tableName)
        );

        long rowsCopied;
        conn.setAutoCommit(false);
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(csvFile), "UTF-8"),
                1 << 20  // 1 МБ буфер чтения
        )) {
            CopyManager copyManager = new CopyManager((BaseConnection) conn);
            rowsCopied = copyManager.copyIn(copySQL, reader);
            conn.commit();
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return (int) rowsCopied;
    }

    private String buildCols(List<String> headers) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < headers.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append(quote(headers.get(i)));
        }
        return sb.toString();
    }

    private String buildPlaceholders(int count) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < count; i++) {
            if (i > 0) sb.append(", ");
            sb.append(placeholder(i));
        }
        return sb.toString();
    }

    private String escapeCsvField(String value) {
        if (value.contains(",") || value.contains("\"") || value.contains("\n")) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }
        return value;
    }
}