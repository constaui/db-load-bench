import java.io.*;
import java.util.*;

/**
 * Статические утилиты разбора CSV-строк.
 *
 * Раньше класс был ещё и in-memory ридером (грузил весь файл в
 * {@code List<String[]>}), что приводило к OutOfMemoryError на больших
 * объёмах. Потоковая часть переехала в {@link CSVStream}; здесь остались
 * только функции разбора одной строки и нормализации идентификаторов,
 * а также потоковый счётчик строк для file_insert.
 */
public class CSVReader {

    /** Разбор одной CSV-строки по правилам RFC 4180 (с lenient-кавычками). */
    public static String[] parseCsvLine(String line) {
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

    /**
     * Определяет line-ending CSV-файла без декодирования.
     * Возвращает строку-аргумент для LOAD DATA LINES TERMINATED BY:
     * {@code "\\r\\n"} (Windows-стиль) или {@code "\\n"}. Без этого
     * LOAD DATA на Windows-файле может потерять разбиение строк и
     * оставить в таблице 1 битую запись.
     */
    public static String detectLinesTerminator(String path) throws IOException {
        try (InputStream is = new FileInputStream(path)) {
            byte[] buf = new byte[8192];
            int n = is.read(buf);
            if (n > 0) {
                for (int i = 0; i + 1 < n; i++) {
                    if (buf[i] == '\r' && buf[i + 1] == '\n') {
                        return "\\r\\n";
                    }
                }
            }
        }
        return "\\n";
    }

    /**
     * Потоковый счётчик непустых строк CSV минус одна (заголовок).
     *
     * Нужен для file_insert: MySQL-драйвер на LOAD DATA INFILE возвращает
     * через executeUpdate() единицу (статус OK-пакета), а не число
     * загруженных строк. Поэтому считаем строки сами одним проходом по
     * файлу, без парсинга и без загрузки в память.
     */
    public static int countDataRows(String path) throws IOException {
        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(new FileInputStream(path), "UTF-8"),
                1 << 20)) {
            int total = 0;
            String line;
            while ((line = br.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                total++;
            }
            return total > 0 ? total - 1 : 0;
        }
    }

    /** Удаляет обрамляющие кавычки/пробелы из идентификатора колонки/значения. */
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
