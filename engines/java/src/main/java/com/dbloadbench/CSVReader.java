import java.io.*;
import java.util.*;

public class CSVReader {

    public final List<String>   headers;
    public final List<String[]> rows;

    public CSVReader(String path) throws IOException {
        headers = new ArrayList<>();
        rows    = new ArrayList<>();

        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(new FileInputStream(path), "UTF-8"))) {

            String line = br.readLine();
            if (line == null) throw new IOException("CSV is empty");

            if (line.startsWith("\uFEFF")) {
                line = line.substring(1);
            }

            String[] rawHeaders = parseLine(line);
            for (String h : rawHeaders) {
                headers.add(cleanIdentifier(h));
            }

            while ((line = br.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] row = parseLine(line);
                for (int i = 0; i < row.length; i++) {
                    row[i] = cleanIdentifier(row[i]);
                }
                rows.add(row);
            }
        }
    }

    private String[] parseLine(String line) {
        line = line.trim();
        return parseCSVLine(line);
    }

    private String[] parseCSVLine(String line) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;

        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);

            if (c == '"') {
                if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (c == ',' && !inQuotes) {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        fields.add(current.toString());

        return fields.toArray(new String[0]);
    }

    public static String cleanIdentifier(String s) {
        if (s == null) return "";
        while (true) {
            String stripped = s.trim()
                               .replaceAll("^\"|\"$", "")
                               .replaceAll("^`|`$", "")
                               .replaceAll("^'|'$", "")
                               .trim();
            if (stripped.equals(s)) break;
            s = stripped;
        }
        return s;
    }
}