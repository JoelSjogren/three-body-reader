package se.joelsjogren.threebodyreader

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.WindowInsets
import android.webkit.WebView
import android.widget.FrameLayout

class MainActivity : Activity() {

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val webView = WebView(this)
        webView.settings.javaScriptEnabled = true
        // poc9 persists fade state in localStorage
        webView.settings.domStorageEnabled = true
        webView.setBackgroundColor(Color.parseColor("#111111"))
        // targetSdk 35 forces edge-to-edge; keep the page out from under the system bars.
        // WebView ignores its own padding, so pad a wrapping FrameLayout instead.
        val container = FrameLayout(this)
        container.setBackgroundColor(Color.parseColor("#111111"))
        container.addView(webView)
        container.setOnApplyWindowInsetsListener { v, insets ->
            if (Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(
                    WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout()
                )
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                WindowInsets.CONSUMED
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(
                    insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                    insets.systemWindowInsetRight, insets.systemWindowInsetBottom
                )
                insets
            }
        }
        setContentView(container)
        webView.loadUrl("file:///android_asset/index.html")
    }
}
