package ar.datas.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
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
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import ar.datas.link.LinkClient
import java.io.IOException
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
    private lateinit var computersBox: LinearLayout

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

        computersBox = findViewById(R.id.computers)
        val linkBtn: Button = findViewById(R.id.linkBtn)
        if (Build.VERSION.SDK_INT < 29) { // the encrypted connection (TLS 1.3) needs Android 10
            findViewById<TextView>(R.id.computersHint).text = getString(R.string.computers_old_android)
            linkBtn.isEnabled = false
        } else {
            linkBtn.setOnClickListener { linkDialog() }
        }
        renderComputers()

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

    // ---- my computers: linked through the encrypted link (ar.datas.link.LinkClient) ----

    private fun renderComputers() {
        computersBox.removeAllViews()
        for (c in Computers.all(this)) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
            }
            val name = TextView(this).apply {
                text = c.name
                setTextColor(0xFFE6E9EE.toInt())
                textSize = 15f
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val open = Button(this).apply {
                text = getString(R.string.computer_open)
                setOnClickListener {
                    startActivity(Intent(this@MainActivity, WindowActivity::class.java).putExtra(WindowActivity.EXTRA_ID, c.id))
                }
            }
            val forget = Button(this).apply {
                text = getString(R.string.computer_forget)
                textSize = 12f
                setOnClickListener {
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle(getString(R.string.computer_forget_title, c.name))
                        .setMessage(R.string.computer_forget_text)
                        .setPositiveButton(R.string.computer_forget) { _, _ ->
                            Computers.forget(this@MainActivity, c.id)
                            renderComputers()
                        }
                        .setNegativeButton(R.string.link_cancel, null)
                        .show()
                }
            }
            row.addView(name)
            row.addView(open)
            row.addView(forget)
            computersBox.addView(row)
        }
    }

    /** Address typed by the person: "192.168.1.20" or "192.168.1.20:8424" (or a name). */
    private fun splitAddress(text: String): Pair<String, Int>? {
        val a = text.trim().removePrefix("http://").removePrefix("https://").trim('/')
        if (a.isEmpty()) return null
        val colon = a.lastIndexOf(':')
        if (colon > 0 && a.indexOf(':') == colon) {
            val port = a.substring(colon + 1).toIntOrNull() ?: return null
            return Pair(a.substring(0, colon), port)
        }
        return Pair(a, LinkClient.DEFAULT_PORT)
    }

    private fun linkDialog() {
        val pad = (16 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, 0)
        }
        val how = TextView(this).apply { text = getString(R.string.link_how); textSize = 14f }
        val nearbyLabel = TextView(this).apply {
            text = getString(R.string.link_nearby)
            textSize = 13f
            visibility = View.GONE
        }
        val nearby = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val address = EditText(this).apply {
            hint = getString(R.string.link_address)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
        }
        val code = EditText(this).apply {
            hint = getString(R.string.link_code)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS or
                android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setSingleLine()
        }
        val message = TextView(this).apply { textSize = 13f }
        box.addView(how)
        box.addView(nearbyLabel)
        box.addView(nearby)
        box.addView(address)
        box.addView(code)
        box.addView(message)

        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.link_title)
            .setView(box)
            .setPositiveButton(R.string.link_go, null) // set below, so a wrong code keeps the dialog open
            .setNegativeButton(R.string.link_cancel, null)
            .create()

        val stopLooking = lookForComputers { shownName, host, port ->
            nearbyLabel.visibility = View.VISIBLE
            val pick = Button(this).apply {
                text = shownName
                isAllCaps = false
                setOnClickListener {
                    address.setText(if (host.contains(':')) "[$host]:$port" else "$host:$port")
                    address.tag = Pair(host, port)
                    code.requestFocus()
                }
            }
            nearby.addView(pick)
        }
        dialog.setOnDismissListener { stopLooking() }
        dialog.show()

        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { button ->
            @Suppress("UNCHECKED_CAST")
            val picked = address.tag as? Pair<String, Int>
            val typed = address.text.toString()
            val target = if (picked != null && typed.contains(picked.first)) picked else splitAddress(typed)
            if (target == null) {
                message.text = getString(R.string.link_need_address)
                return@setOnClickListener
            }
            button.isEnabled = false
            message.text = getString(R.string.link_working)
            val phoneName = (Build.MANUFACTURER.replaceFirstChar { it.uppercase() } + " " + Build.MODEL).trim()
            val typedCode = code.text.toString()
            Thread {
                var linked: LinkClient.Computer? = null
                var problem = ""
                try {
                    linked = LinkClient.pair(target.first, target.second, typedCode, phoneName, "android")
                } catch (e: LinkClient.LinkException) {
                    problem = e.message ?: ""
                } catch (e: IOException) {
                    problem = getString(R.string.link_unreachable)
                }
                ui.post {
                    if (isFinishing) return@post
                    val done = linked
                    if (done != null) {
                        Computers.save(this, done)
                        renderComputers()
                        Toast.makeText(this, getString(R.string.link_done, done.name), Toast.LENGTH_LONG).show()
                        dialog.dismiss()
                    } else {
                        message.text = problem
                        button.isEnabled = true
                    }
                }
            }.start()
        }
    }

    /**
     * Computers with Datas on this Wi-Fi that accept links (they announce themselves; this only
     * tells the name and address — linking still needs the code). Returns how to stop looking.
     */
    private fun lookForComputers(found: (String, String, Int) -> Unit): () -> Unit {
        val nsd = getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return {}
        val waiting = ArrayDeque<NsdServiceInfo>()
        val seen = HashSet<String>()
        var resolving = false
        var stopped = false

        fun next() {
            val info: NsdServiceInfo
            synchronized(waiting) {
                if (resolving || stopped || waiting.isEmpty()) return
                info = waiting.removeFirst()
                resolving = true
            }
            try {
                @Suppress("DEPRECATION")
                nsd.resolveService(info, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                        synchronized(waiting) { resolving = false }
                        next()
                    }

                    override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                        @Suppress("DEPRECATION")
                        val host = serviceInfo.host?.hostAddress?.substringBefore('%')
                        val named = serviceInfo.attributes["name"]?.let { String(it, Charsets.UTF_8) }
                        val shown = if (named.isNullOrBlank()) serviceInfo.serviceName else named
                        if (host != null) {
                            ui.post { if (!stopped && seen.add("$host:${serviceInfo.port}")) found(shown, host, serviceInfo.port) }
                        }
                        synchronized(waiting) { resolving = false }
                        next()
                    }
                })
            } catch (e: RuntimeException) {
                synchronized(waiting) { resolving = false }
            }
        }

        val listener = object : NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onServiceLost(serviceInfo: NsdServiceInfo) {}
            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                synchronized(waiting) { waiting.addLast(serviceInfo) }
                next()
            }
        }
        try {
            nsd.discoverServices("_datas-link._tcp", NsdManager.PROTOCOL_DNS_SD, listener)
        } catch (e: RuntimeException) {
            return {}
        }
        return {
            stopped = true
            try {
                nsd.stopServiceDiscovery(listener)
            } catch (e: RuntimeException) {
                // it had not started, or was already stopped
            }
        }
    }

    override fun onResume() {
        super.onResume()
        renderComputers()
    }

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
