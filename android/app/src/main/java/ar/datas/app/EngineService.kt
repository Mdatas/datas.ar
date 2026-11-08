package ar.datas.app

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

/** Foreground service that owns the llama-server process so Android keeps it alive. */
class EngineService : Service() {
    private var process: Process? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var watcher: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) return START_NOT_STICKY
        when (intent.action) {
            ACTION_STOP -> { stopEngine(); stopSelf(); return START_NOT_STICKY }
            ACTION_START -> {
                val cmd = intent.getStringArrayListExtra(EXTRA_CMD) ?: return START_NOT_STICKY
                val label = intent.getStringExtra(EXTRA_LABEL) ?: "model"
                startInForeground(label)
                stopEngine()
                try {
                    Engine.logFile(this).appendText("\n=== starting: ${cmd.joinToString(" ")}\n")
                    process = Engine.start(this, cmd)
                    status = Status.STARTING
                    lastLabel = label
                    acquireWakeLock()
                    watcher = Thread {
                        val p = process
                        val code = try { p?.waitFor() ?: -1 } catch (_: InterruptedException) { -1 }
                        if (process === p) {
                            status = Status.STOPPED
                            lastError = if (code != 0) "exit code $code" else null
                            releaseWakeLock()
                            stopForegroundCompat()
                            stopSelf()
                        }
                    }.also { it.isDaemon = true; it.start() }
                    Thread {
                        val deadline = System.currentTimeMillis() + 180_000
                        while (System.currentTimeMillis() < deadline && status == Status.STARTING) {
                            if (Engine.healthy()) { status = Status.RUNNING; break }
                            try { Thread.sleep(700) } catch (_: InterruptedException) { break }
                        }
                        if (status == Status.STARTING) { lastError = "health check timed out"; stopEngine(); stopSelf() }
                    }.also { it.isDaemon = true; it.start() }
                } catch (e: Exception) {
                    lastError = e.message ?: e.toString()
                    status = Status.STOPPED
                    stopSelf()
                }
            }
        }
        return START_NOT_STICKY
    }

    private fun startInForeground(label: String) {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, EngineService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val n: Notification = NotificationCompat.Builder(this, DatasApp.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(getString(R.string.notif_title))
            .setContentText(getString(R.string.notif_text, label))
            .setContentIntent(open)
            .addAction(0, getString(R.string.stop), stop)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }

    @Suppress("DEPRECATION")
    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            stopForeground(true)
        }
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "datas:engine").also { it.acquire(6 * 60 * 60 * 1000L) }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun stopEngine() {
        val p = process
        process = null
        p?.destroy()
        status = Status.STOPPED
        releaseWakeLock()
        stopForegroundCompat()
    }

    override fun onDestroy() {
        stopEngine()
        super.onDestroy()
    }

    enum class Status { STOPPED, STARTING, RUNNING }

    companion object {
        const val ACTION_START = "ar.datas.app.START"
        const val ACTION_STOP = "ar.datas.app.STOP"
        const val EXTRA_CMD = "cmd"
        const val EXTRA_LABEL = "label"
        const val NOTIF_ID = 4201

        @Volatile var status: Status = Status.STOPPED
        @Volatile var lastError: String? = null
        @Volatile var lastLabel: String = ""

        fun start(ctx: Context, cmd: List<String>, label: String) {
            val i = Intent(ctx, EngineService::class.java).setAction(ACTION_START)
                .putStringArrayListExtra(EXTRA_CMD, ArrayList(cmd)).putExtra(EXTRA_LABEL, label)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i) else ctx.startService(i)
        }

        fun stop(ctx: Context) {
            ctx.startService(Intent(ctx, EngineService::class.java).setAction(ACTION_STOP))
        }
    }
}
