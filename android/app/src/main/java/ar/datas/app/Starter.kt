package ar.datas.app

import android.content.Context
import java.io.File

/**
 * The small starter AI shipped inside the APK (assets/starter/, put there by the build from
 * scripts/fetch_starter.py, checked against its SHA-256): copied once to where downloaded AIs
 * live, so the phone has an AI to ask from the first minute, without a download.
 */
object Starter {
    const val ID = "qwen3-0.6b"
    const val QUANT = "Q4_0"

    /** True when the starter is (now) among the phone's AIs. Runs on a background thread. */
    fun placeShipped(ctx: Context, models: List<Model>): Boolean {
        val m = models.firstOrNull { it.id == ID } ?: return false
        val f = m.files.firstOrNull { it.quant == QUANT } ?: return false
        if (Downloader.isDownloaded(ctx, m, f)) return true
        val shipped = try { ctx.assets.list("starter")?.toList() ?: emptyList() } catch (e: Exception) { emptyList() }
        if (f.path !in shipped) return false
        val dest = Downloader.localFile(ctx, m, f)
        dest.parentFile?.mkdirs()
        val part = File(dest.path + ".part")
        ctx.assets.open("starter/${f.path}").use { input -> part.outputStream().use { input.copyTo(it, 1 shl 20) } }
        if (part.length() != f.bytes) { part.delete(); return false }
        return part.renameTo(dest)
    }
}
