import java.io.FileInputStream
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Optional release signing: android/keystore.properties (git-ignored) or env vars set by CI.
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) load(FileInputStream(f))
}
fun prop(name: String): String? = (keystoreProps.getProperty(name) ?: System.getenv(name))?.takeIf { it.isNotBlank() }

android {
    namespace = "ar.datas.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "ar.datas.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 8
        versionName = "0.6.1"
        ndk { abiFilters += listOf("arm64-v8a") }
    }

    signingConfigs {
        if (prop("KEYSTORE_FILE") != null) {
            create("release") {
                storeFile = file(prop("KEYSTORE_FILE")!!)
                storePassword = prop("KEYSTORE_PASSWORD")
                keyAlias = prop("KEY_ALIAS")
                keyPassword = prop("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (prop("KEYSTORE_FILE") != null) signingConfigs.getByName("release")
                            else signingConfigs.getByName("debug")
        }
    }

    // llama-server is an executable shipped as lib<name>.so; Android only allows exec of
    // files in the app's native library dir, which requires extraction (legacy packaging).
    packaging {
        jniLibs {
            useLegacyPackaging = true
            keepDebugSymbols += listOf("**/*.so")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.google.android.material:material:1.12.0")
}
