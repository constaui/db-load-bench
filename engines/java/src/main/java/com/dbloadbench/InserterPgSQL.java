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

    // ─── defaultInsert ────────────────────────────────────────────────────────

    @Override
    public int defaultInsert(String csvFile, String tableName) throws Exception {
        CSVReader data = new CSVReader(csvFile);

        String cols = buildCols(data.headers);
        String phs  = buildPlaceholders(data.headers.size());
        String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                    quote(tableName), cols, phs);

        conn.setAutoCommit(false);
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            for (String[] row : data.rows) {
                for (int i = 0; i < row.length; i++) {
                    ps.setString(i + 1, row[i]);
                }
                ps.executeUpdate();
            }
            conn.commit();
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return data.rows.size();
    }

    // ─── bulkInsert ───────────────────────────────────────────────────────────

    @Override
    public int bulkInsert(String csvFile, String tableName, int batchSize) throws Exception {
        CSVReader data = new CSVReader(csvFile);

        String cols = buildCols(data.headers);
        String phs  = buildPlaceholders(data.headers.size());
        String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                    quote(tableName), cols, phs);

        conn.setAutoCommit(false);
        int total = 0;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            int count = 0;
            for (String[] row : data.rows) {
                for (int i = 0; i < row.length; i++) {
                    ps.setString(i + 1, row[i]);
                }
                ps.addBatch();
                count++;

                if (count % batchSize == 0) {
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
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return total;
    }

    // ─── fileInsert — COPY FROM STDIN ─────────────────────────────────────────

    @Override
    public int fileInsert(String csvFile, String tableName) throws Exception {
        CSVReader data = new CSVReader(csvFile);

        StringBuilder buf = new StringBuilder();
        for (int i = 0; i < data.headers.size(); i++) {
            if (i > 0) buf.append(",");
            buf.append(escapeCsvField(data.headers.get(i)));
        }
        buf.append("\n");
        for (String[] row : data.rows) {
            for (int i = 0; i < row.length; i++) {
                if (i > 0) buf.append(",");
                buf.append(escapeCsvField(row[i]));
            }
            buf.append("\n");
        }

        String copySQL = String.format(
            "COPY %s FROM STDIN WITH (FORMAT csv, HEADER true)",
            quote(tableName)
        );

        conn.setAutoCommit(false);
        try {
            CopyManager copyManager = new CopyManager((BaseConnection) conn);
            copyManager.copyIn(copySQL, new StringReader(buf.toString()));
            conn.commit();
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return data.rows.size();
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

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