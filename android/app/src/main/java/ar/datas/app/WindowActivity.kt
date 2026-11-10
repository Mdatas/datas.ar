package ar.datas.app

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import ar.datas.link.LinkClient

/**
 * A linked computer's Datas, full screen. The page is asked from a door on this phone
 * (127.0.0.1); the door carries everything, encrypted, to that computer (LinkClient.Door).
 */
class WindowActivity : AppCompatActivity() {
    private var door: LinkClient.Door? = null
    private var web: WebView? = null
    private var filePick: ValueCallback<Array<Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val computer = Computers.find(this, intent.getStringExtra(EXTRA_ID) ?: "")
        if (computer == null) {
            finish()
            return
        }
        title = computer.name
        val view = WebView(this)
        web = view
        setContentView(view)
        view.settings.javaScriptEnabled = true
        view.settings.domStorageEnabled = true
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (url.host == "127.0.0.1") return false
                openOutside(url) // a link to a web page: the phone's browser shows it
                return true
            }
        }
        view.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                v: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams
            ): Boolean {
                filePick?.onReceiveValue(null)
                filePick = callback
                return try {
                    @Suppress("DEPRECATION")
                    startActivityForResult(params.createIntent(), PICK_FILE)
                    true
                } catch (e: ActivityNotFoundException) {
                    filePick = null
                    false
                }
            }
        }
        Thread {
            try {
                val d = LinkClient.Door(computer)
                door = d
                runOnUiThread { if (!isFinishing) view.loadUrl(d.url()) }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this, getString(R.string.link_failed, e.message ?: ""), Toast.LENGTH_LONG).show()
                    finish()
                }
            }
        }.start()
    }

    private fun openOutside(url: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, url))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, url.toString(), Toast.LENGTH_LONG).show()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == PICK_FILE) {
            filePick?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            filePick = null
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val view = web
        if (view != null && view.canGoBack()) {
            view.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        door?.close()
        web?.destroy()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_ID = "computer"
        private const val PICK_FILE = 71
    }
}
