// Standalone headless report; the resulting file is a job artifact.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class QoderExport extends GhidraScript {
    private String quote(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            if (c == '\\' || c == '"') result.append('\\').append(c);
            else if (c < 32) result.append(String.format("\\u%04x", (int)c));
            else result.append(c);
        }
        return result.append('"').toString();
    }
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected report path");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (BufferedWriter out = Files.newBufferedWriter(Paths.get(args[0]), StandardCharsets.UTF_8)) {
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            int count = 0;
            while (functions.hasNext() && !monitor.isCancelled() && count++ < 10000) {
                Function function = functions.next();
                DecompileResults result = decompiler.decompileFunction(function, 15, monitor);
                String code = result.decompileCompleted() ? result.getDecompiledFunction().getC() : "";
                out.write("{\"name\":" + quote(function.getName()) + ",\"address\":" + quote(function.getEntryPoint().toString())
                    + ",\"decompiled\":" + result.decompileCompleted() + ",\"code\":" + quote(code) + "}\n");
            }
        } finally { decompiler.dispose(); }
    }
}
