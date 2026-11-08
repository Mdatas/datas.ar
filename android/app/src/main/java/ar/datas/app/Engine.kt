package ar.datas.app

import android.content.Context
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * llama-server, shipped inside the APK as lib/arm64-v8a/libllama-server.so (a PIE executable
 * renamed so the package manager extracts it into the app's native library dir — the only
 * place Android ≥10 allows an app to exec from). Its shared libraries sit next to it.
 */
object Engine {
    const val PORT = 8421
    const val BASE_URL = "http://127.0.0.1:$PORT"

    fun binary(ctx: Context): File = File(ctx.applicationInfo.nativeLibraryDir, "libllama-server.so")

    fun logFile(ctx: Context): File = File(ctx.filesDir, "llama-server.log")

    fun isBundled(ctx: Context): Boolean = binary(ctx).exists()

    /** Flags mirror datas/recommend/engine.py::llama_server_args (phone = CPU placement). */
    fun command(ctx: Context, modelPath: String, context: Int, threads: Int, headroomBytes: Long, kvBits: Int): List<String> {
        val cmd = arrayListOf(
            binary(ctx).absolutePath,
            "-m", modelPath,
            "--host", "127.0.0.1", "--port", PORT.toString(),
            "-c", context.toString(),
            "-t", threads.toString(),
            "--jinja",
            "-fa", "auto",
            "--fit", "on",
            "--fit-target", maxOf(256L, headroomBytes / (1024 * 1024)).toString(),
            "-ngl", "0",
            "--no-warmup",
        )
        if (kvBits == 8) cmd.addAll(listOf("-ctk", "q8_0", "-ctv", "q8_0"))
        return cmd
    }

    fun start(ctx: Context, cmd: List<String>): Process {
        val libDir = ctx.applicationInfo.nativeLibraryDir
        val pb = ProcessBuilder(cmd)
            .directory(ctx.filesDir)
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.appendTo(logFile(ctx)))
        pb.environment()["LD_LIBRARY_PATH"] = libDir
        pb.environment()["GGML_BACKEND_PATH"] = libDir   // where libggml-cpu-*.so variants live
        pb.environment()["HOME"] = ctx.filesDir.absolutePath
        pb.environment()["TMPDIR"] = ctx.cacheDir.absolutePath
        return pb.start()
    }

    fun healthy(): Boolean = try {
        val c = URL("$BASE_URL/health").openConnection() as HttpURLConnection
        c.connectTimeout = 1500; c.readTimeout = 1500
        val ok = c.responseCode == 200
        c.disconnect()
        ok
    } catch (_: Exception) { false }

    fun logTail(ctx: Context, lines: Int = 30): String {
        val f = logFile(ctx)
        if (!f.exists()) return ""
        return f.readLines().takeLast(lines).joinToString("\n")
    }
}
