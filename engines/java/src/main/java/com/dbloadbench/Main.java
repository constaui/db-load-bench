public class Main {

    public static void main(String[] args) throws Exception {
        String method    = getArg(args, "--method",     "default_insert");
        String csvFile   = getArg(args, "--csv",        null);
        String tableName = getArg(args, "--table",      "Test");
        String dbType    = getArg(args, "--db-type",    "mysql");
        String host      = getArg(args, "--host",       "localhost");
        int    port      = Integer.parseInt(getArg(args, "--port", "3306"));
        String user      = getArg(args, "--user",       "");
        String password  = getArg(args, "--password",   "");
        String database  = getArg(args, "--database",   "");
        int    batchSize = Integer.parseInt(getArg(args, "--batch-size", "1000"));

        if (csvFile == null) {
            System.err.println("error: --csv is required");
            System.exit(1);
        }

        ConnParams params = new ConnParams(host, port, user, password, database);

        Inserter inserter;
        switch (dbType) {
            case "mysql"      -> inserter = new InserterMySQL(params);
            case "postgresql" -> inserter = new InserterPgSQL(params);
            default -> {
                System.err.println("unsupported db type: " + dbType);
                System.exit(1);
                return;
            }
        }

        long   start   = System.nanoTime();
        int    rows    = 0;

        try (inserter) {
            rows = switch (method) {
                case "default_insert" -> inserter.defaultInsert(csvFile, tableName);
                case "bulk_insert"    -> inserter.bulkInsert(csvFile, tableName, batchSize);
                case "file_insert"    -> inserter.fileInsert(csvFile, tableName);
                default -> {
                    System.err.println("unknown method: " + method);
                    System.exit(1);
                    yield 0;
                }
            };
        } catch (Exception e) {
            System.err.println("insert error: " + e.getMessage());
            System.exit(1);
        }

        double  elapsed   = (System.nanoTime() - start) / 1_000_000_000.0;
        Integer batchArg  = method.equals("bulk_insert") ? batchSize : null;

        Result result = Result.build(dbType, method, rows, elapsed, batchArg);
        System.out.println(result.toJson());
    }

    private static String getArg(String[] args, String key, String defaultVal) {
        for (int i = 0; i < args.length - 1; i++) {
            if (args[i].equals(key)) return args[i + 1];
        }
        return defaultVal;
    }
}