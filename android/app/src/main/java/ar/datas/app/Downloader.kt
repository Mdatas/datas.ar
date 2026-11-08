package ar.datas.app

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import java.io.File

/**
 * Model downloads via Android's DownloadManager: resumable, survives app restarts, shows a
 * system notification, no extra permissions for app-specific external storage.
 */
object Downloader {
    fun modelsDir(ctx: Context): File = File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "models")

    fun localFile(ctx: Context, m: Model, f: ModelFile): File = File(File(modelsDir(ctx), m.id), f.path)

    fun isDownloaded(ctx: Context, m: Model, f: ModelFile): Boolean {
        val file = localFile(ctx, m, f)
        return file.exists() && file.length() == f.bytes
    }

    data class Progress(val status: Int, val done: Long, val total: Long, val reason: Int) {
        val percent: Int get() = if (total > 0) ((done * 100) / total).toInt() else 0
        val finished: Boolean get() = status == DownloadManager.STATUS_SUCCESSFUL
        val failed: Boolean get() = status == DownloadManager.STATUS_FAILED
    }

    fun enqueue(ctx: Context, m: Model, f: ModelFile): Long {
        val dm = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val dest = localFile(ctx, m, f)
        dest.parentFile?.mkdirs()
        if (dest.exists()) dest.delete()
        val req = DownloadManager.Request(Uri.parse(m.url(f)))
            .setTitle("Datas · ${m.name} ${f.quant}")
            .setDescription(f.path)
            .setDestinationUri(Uri.fromFile(dest))
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(false)
        return dm.enqueue(req)
    }

    fun progress(ctx: Context, id: Long): Progress? {
        val dm = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        dm.query(DownloadManager.Query().setFilterById(id)).use { c ->
            if (!c.moveToFirst()) return null
            val status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
            val done = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR))
            val total = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES))
            val reason = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
            return Progress(status, done, total, reason)
        }
    }

    fun installed(ctx: Context): List<File> =
        modelsDir(ctx).walkTopDown().filter { it.isFile && it.name.endsWith(".gguf") }.toList()
}
