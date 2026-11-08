package ar.datas.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var device: DeviceInfo
    private lateinit var models: List<Model>
    private var rec: Recommender.Recommendation? = null
    private val ui = Handler(Looper.getMainLooper())
    private var downloadId: Long = -1
    private var pending: Recommender.Candidate? = null

    private val headroomSteps = intArrayOf(5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60)
    private val contexts = intArrayOf(2048, 4096, 8192, 16384)

    private lateinit var statusTv: TextView
    private lateinit var deviceTv: TextView
    private lateinit var deviceNote: TextView
    private lateinit var headroomSeek: SeekBar
    private lateinit var headroomLabel: TextView
    private lateinit var contextSpin: Spinner
    private lateinit var kv8: CheckBox
    private lateinit var recoName: TextView
    private lateinit var recoChips: TextView
    private lateinit var recoNeeds: TextView
    private lateinit var recoLicense: TextView
    private lateinit var fitBar: ProgressBar
    private lateinit var installBtn: Button
    private lateinit var progress: ProgressBar
    private lateinit var progressText: TextView
    private lateinit var others: LinearLayout
    private lateinit var web: WebView
    private lateinit var chatHint: TextView
    private lateinit var stopBtn: Button

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusTv = findViewById(R.id.status); deviceTv = findViewById(R.id.deviceText); deviceNote = findViewById(R.id.deviceNote)
        headroomSeek = findViewById(R.id.headroom); headroomLabel = findViewById(R.id.headroomLabel)
        contextSpin = findViewById(R.id.context); kv8 = findViewById(R.id.kv8)
        recoName = findViewById(R.id.recoName); recoChips = findViewById(R.id.recoChips); recoNeeds = findViewById(R.id.recoNeeds)
        recoLicense = findViewById(R.id.recoLicense); fitBar = findViewById(R.id.fitBar); installBtn = findViewById(R.id.installRun)
        progress = findViewById(R.id.progress); progressText = findViewById(R.id.progressText); others = findViewById(R.id.others)
        web = findViewById(R.id.web); chatHint = findViewById(R.id.chatHint); stopBtn = findViewById(R.id.stopBtn)

        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }

        device = DeviceInfo.detect(this)
        models = Catalog.load(this)
        renderDevice()

        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = WebViewClient()

        headroomSeek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, p: Int, fromUser: Boolean) { updateHeadroomLabel(); if (fromUser) recompute() }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {}
        })
        contextSpin.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, contexts.map { "${it / 1024}k" })
        contextSpin.setSelection(1)
        contextSpin.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) { recompute() }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        kv8.setOnCheckedChangeListener { _, _ -> recompute() }
        stopBtn.setOnClickListener { EngineService.stop(this); ui.postDelayed({ refreshStatus() }, 800) }

        if (!device.isArm64) {
            recoName.text = getString(R.string.unsupported_abi); installBtn.isEnabled = false
        } else if (!Engine.isBundled(this)) {
            recoName.text = "This APK was built without the llama.cpp binaries (see android/README.md)."; installBtn.isEnabled = false
        } else {
            recompute()
        }
        ui.post(statusPoller)
    }

    private fun headroom(): Double = headroomSteps[headroomSeek.progress.coerceIn(0, headroomSteps.size - 1)] / 100.0
    private fun context(): Int = contexts[contextSpin.selectedItemPosition.coerceIn(0, contexts.size - 1)]

    private fun updateHeadroomLabel() {
        val pct = (headroom() * 100).toInt()
        val keep = maxOf(Recommender.HEADROOM_MIN_GIB, device.ramGiB * headroom())
        headroomLabel.text = getString(R.string.headroom_label, pct, keep)
    }

    private fun renderDevice() {
        val g = DeviceInfo.GIB
        deviceTv.text = String.format(
            Locale.US, "%s\n%s · %d cores · %s\nRAM %.1f GiB (%.1f free now) · storage %.1f GiB free",
            device.androidVersion, device.soc, device.cores, device.abi, device.ramTotal / g, device.ramAvailable / g, device.diskFree / g
        )
        deviceNote.text = if (device.onBattery) getString(R.string.battery_hint) else ""
        updateHeadroomLabel()
    }

    private fun recompute() {
        if (!device.isArm64 || !Engine.isBundled(this)) return
        val r = Recommender.recommend(models, device, headroom(), context(), if (kv8.isChecked) 8 else 16)
        rec = r
        val g = DeviceInfo.GIB
        val d = r.default
        others.removeAllViews()
        if (d == null) {
            recoName.text = getString(R.string.no_fit); recoChips.text = ""; recoNeeds.text = ""; recoLicense.text = ""
            installBtn.isEnabled = false; fitBar.progress = 0
            return
        }
        installBtn.isEnabled = EngineService.status == EngineService.Status.STOPPED
        recoName.text = "${d.model.name}  ·  ${d.file.quant}"
        recoChips.text = "${d.speedClass} · ${d.fitLevel} · tier ${d.model.qualityTier}/5 · ${d.model.capabilities.joinToString(" ")}"
        fitBar.progress = ((d.need.total * 100) / maxOf(1L, r.budget.ramBudget)).toInt().coerceIn(0, 100)
        recoNeeds.text = getString(R.string.needs, d.need.total / g, d.need.weights / g, d.need.kvCache / g, d.need.overhead / g, r.budget.ramBudget / g) +
            (if (d.need.kvExact) "" else " · KV estimated")
        recoLicense.text = "${d.model.vendor} · license: ${d.model.license}${if (d.model.licenseSource == "unverified") " (unverified)" else ""} · ${d.model.hfRepo}"
        installBtn.text = if (Downloader.isDownloaded(this, d.model, d.file)) getString(R.string.run) else getString(R.string.install_run)
        installBtn.setOnClickListener { installAndRun(d) }
        for (c in r.fits) {
            if (c.model.id == d.model.id) continue
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val tv = TextView(this).apply {
                text = String.format(Locale.US, "%s %s · %.1f GiB · %s", c.model.name, c.file.quant, c.need.total / g, c.speedClass)
                setTextColor(0xFFE6E9EE.toInt()); textSize = 13f
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val b = Button(this).apply {
                text = if (Downloader.isDownloaded(this@MainActivity, c.model, c.file)) getString(R.string.run) else getString(R.string.install_run)
                textSize = 12f
                setOnClickListener { installAndRun(c) }
            }
            row.addView(tv); row.addView(b)
            others.addView(row)
        }
    }

    private fun installAndRun(c: Recommender.Candidate) {
        pending = c
        installBtn.isEnabled = false
        if (Downloader.isDownloaded(this, c.model, c.file)) { startEngine(c); return }
        progress.visibility = View.VISIBLE; progress.progress = 0
        progressText.text = getString(R.string.downloading, c.file.path, 0)
        downloadId = Downloader.enqueue(this, c.model, c.file)
        ui.postDelayed(downloadPoller, 1000)
    }

    private val downloadPoller = object : Runnable {
        override fun run() {
            val c = pending ?: return
            val p = Downloader.progress(this@MainActivity, downloadId)
            if (p == null) { progressText.text = "download lost"; installBtn.isEnabled = true; return }
            progress.progress = p.percent
            progressText.text = getString(R.string.downloading, c.file.path, p.percent) +
                String.format(Locale.US, "  %.2f / %.2f GiB", p.done / DeviceInfo.GIB, maxOf(p.total, c.file.bytes) / DeviceInfo.GIB)
            when {
                p.finished -> {
                    val f = Downloader.localFile(this@MainActivity, c.model, c.file)
                    if (f.length() != c.file.bytes) {
                        progressText.text = "size mismatch (${f.length()} vs ${c.file.bytes}) — file removed, try again"
                        f.delete(); installBtn.isEnabled = true
                    } else startEngine(c)
                }
                p.failed -> { progressText.text = "download failed (reason ${p.reason})"; installBtn.isEnabled = true }
                else -> ui.postDelayed(this, 1000)
            }
        }
    }

    private fun startEngine(c: Recommender.Candidate) {
        val r = rec ?: return
        val path = Downloader.localFile(this, c.model, c.file).absolutePath
        val cmd = Engine.command(this, path, c.need.context, r.budget.threads, r.budget.ramHeadroom, if (kv8.isChecked) 8 else 16)
        progress.visibility = View.GONE
        progressText.text = getString(R.string.starting)
        EngineService.lastError = null
        EngineService.start(this, cmd, "${c.model.name} ${c.file.quant}")
    }

    private val statusPoller = object : Runnable {
        override fun run() { refreshStatus(); ui.postDelayed(this, 1500) }
    }

    private fun refreshStatus() {
        when (EngineService.status) {
            EngineService.Status.RUNNING -> {
                statusTv.text = getString(R.string.running, EngineService.lastLabel)
                chatHint.text = "OpenAI-compatible API: ${Engine.BASE_URL}/v1"
                stopBtn.isEnabled = true; installBtn.isEnabled = false
                pending = null; downloadId = -1
                if (web.visibility != View.VISIBLE) {
                    web.visibility = View.VISIBLE
                    web.loadUrl("${Engine.BASE_URL}/")
                    progressText.text = ""
                }
            }
            EngineService.Status.STARTING -> {
                statusTv.text = getString(R.string.starting); stopBtn.isEnabled = true
            }
            EngineService.Status.STOPPED -> {
                statusTv.text = getString(R.string.stopped)
                chatHint.text = getString(R.string.stopped)
                stopBtn.isEnabled = false
                if (web.visibility == View.VISIBLE) { web.visibility = View.GONE; web.loadUrl("about:blank") }
                val err = EngineService.lastError
                if (err != null) {
                    progressText.text = getString(R.string.error_engine, err) + "\n" + Engine.logTail(this, 12)
                    EngineService.lastError = null; pending = null; downloadId = -1
                }
                if (rec?.default != null && pending == null) installBtn.isEnabled = true
            }
        }
    }

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
