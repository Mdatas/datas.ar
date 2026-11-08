package ar.datas.app

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.StatFs

/** What the recommender needs to know about this phone. Read, never inferred. */
data class DeviceInfo(
    val abi: String,
    val soc: String,
    val cores: Int,
    val ramTotal: Long,
    val ramAvailable: Long,
    val diskFree: Long,
    val onBattery: Boolean,
    val androidVersion: String,
) {
    val isArm64: Boolean get() = abi == "arm64-v8a"
    val ramGiB: Double get() = ramTotal / GIB
    val isQualcomm: Boolean get() = soc.lowercase().let { it.contains("qualcomm") || it.contains("snapdragon") || it.startsWith("sm") || it.contains("adreno") }

    companion object {
        const val GIB = 1024.0 * 1024.0 * 1024.0

        fun detect(ctx: Context): DeviceInfo {
            val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val mi = ActivityManager.MemoryInfo()
            am.getMemoryInfo(mi)
            val modelsDir = Downloader.modelsDir(ctx)
            modelsDir.mkdirs()
            val stat = StatFs(modelsDir.path)
            val soc = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                "${Build.SOC_MANUFACTURER} ${Build.SOC_MODEL}".trim()
            } else {
                Build.HARDWARE ?: "unknown"
            }
            val battery = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val plugged = battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0
            return DeviceInfo(
                abi = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
                soc = soc,
                cores = Runtime.getRuntime().availableProcessors(),
                ramTotal = mi.totalMem,
                ramAvailable = mi.availMem,
                diskFree = stat.availableBytes,
                onBattery = plugged == 0,
                androidVersion = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
            )
        }
    }
}
