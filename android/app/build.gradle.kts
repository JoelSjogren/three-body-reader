plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

// Assemble the demo page into assets/ at build time, mirroring demo.py:
// poc9.html gets chapter1.js injected in <head> and an initReader call at </body>.
// Chapter data lives in ../example-data (never committed), so assets are generated, not checked in.
val repoRoot = rootDir.parentFile
val demoAssetsDir = layout.buildDirectory.dir("generated/demoAssets")
val bundleDemoAssets = tasks.register("bundleDemoAssets") {
    val poc9 = File(repoRoot, "poc9.html")
    val charstats = File(repoRoot, "charstats.js")
    val chapter = File(repoRoot, "example-data/chapter1_ver4.js")
    val outDir = demoAssetsDir
    inputs.files(poc9, charstats, chapter)
    outputs.dir(outDir)
    doLast {
        val dir = outDir.get().asFile
        dir.mkdirs()
        charstats.copyTo(File(dir, "charstats.js"), overwrite = true)
        chapter.copyTo(File(dir, "chapter1.js"), overwrite = true)
        // Android WebView has no Web Speech API; without this shim the main script dies at load
        val speechShim = """
            <script>
            if (!('speechSynthesis' in window)) {
              window.SpeechSynthesisUtterance = function () {};
              window.speechSynthesis = {
                speak: function () {}, cancel: function () {}, pause: function () {}, resume: function () {},
                getVoices: function () { return []; },
                addEventListener: function () {}, removeEventListener: function () {},
                speaking: false, pending: false, paused: false
              };
            }
            </script>
        """.trimIndent()
        // The system-bar insets already provide top/bottom spacing; poc9's 2rem body
        // padding on top of that reads as a large blank band on a phone
        val paddingOverride = "<style>body { padding: 0.5rem 0.9rem 2rem; }</style>"
        val html = poc9.readText()
            .replaceFirst("</head>", "$speechShim\n$paddingOverride\n<script src=\"chapter1.js\"></script>\n</head>")
            .replaceFirst("</body>", "<script>if(window.CHAPTER1)initReader(window.CHAPTER1);</script>\n</body>")
        File(dir, "index.html").writeText(html)
    }
}

android {
    namespace = "se.joelsjogren.threebodyreader"
    compileSdk = 35

    defaultConfig {
        applicationId = "se.joelsjogren.threebodyreader"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    sourceSets["main"].assets.srcDir(demoAssetsDir)

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// srcDir alone carries no task dependency; hook the generator into every variant's asset merge
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(bundleDemoAssets)
}
