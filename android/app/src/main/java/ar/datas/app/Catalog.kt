package ar.datas.app

import android.content.Context
import org.json.JSONObject

/** Same schema as datas/catalog/models.json in the Python package (copied into assets). */
data class KvHint(val layers: Int, val kvHeads: Int, val headDim: Int) {
    fun bytesPerToken(cacheBits: Int = 16): Long = 2L * layers * kvHeads * headDim * (cacheBits / 8)
}

data class ModelFile(val quant: String, val path: String, val bytes: Long)

data class Model(
    val id: String,
    val name: String,
    val vendor: String,
    val paramsB: Double?,
    val activeParamsB: Double?,
    val arch: String,
    val license: String,
    val licenseSource: String,
    val capabilities: List<String>,
    val qualityTier: Int,
    val role: String,
    val hfRepo: String,
    val kv: KvHint?,
    val files: List<ModelFile>,
) {
    fun url(f: ModelFile) = "https://huggingface.co/$hfRepo/resolve/main/${f.path}"

    fun paramsEstimate(f: ModelFile): Double =
        paramsB ?: ((f.bytes * 8.0 / Catalog.bitsPerWeight(f.quant)) / 1e9)

    fun activeEstimate(f: ModelFile): Double =
        activeParamsB ?: if (arch == "moe") paramsEstimate(f) / 8 else paramsEstimate(f)
}

object Catalog {
    // Nominal bits per weight for GGUF quant types (used only to derive a param count when the
    // catalog doesn't state one, and for the low-bit quality penalty).
    private val BPW = mapOf(
        "F32" to 32.0, "F16" to 16.0, "BF16" to 16.0, "Q8_0" to 8.5, "Q6_K" to 6.56,
        "Q5_K_M" to 5.69, "Q5_K_S" to 5.54, "Q5_0" to 5.5, "Q4_K_M" to 4.85, "Q4_K_S" to 4.58,
        "Q4_0" to 4.55, "Q4_1" to 5.0, "IQ4_NL" to 4.5, "IQ4_XS" to 4.25, "MXFP4" to 4.25,
        "Q3_K_M" to 3.91, "Q3_K_S" to 3.5, "Q3_K_L" to 4.27, "IQ3_XXS" to 3.06, "Q2_K" to 3.35,
        "UD-Q2_K_XL" to 3.5, "UD-Q3_K_XL" to 4.3, "UD-Q4_K_XL" to 5.0,
    )

    fun bitsPerWeight(quant: String): Double = BPW[quant.uppercase()] ?: 4.85

    fun load(ctx: Context): List<Model> {
        val text = ctx.assets.open("models.json").bufferedReader().use { it.readText() }
        val root = JSONObject(text)
        val arr = root.getJSONArray("models")
        val out = ArrayList<Model>()
        for (i in 0 until arr.length()) {
            val m = arr.getJSONObject(i)
            val files = ArrayList<ModelFile>()
            val fa = m.getJSONArray("files")
            for (j in 0 until fa.length()) {
                val f = fa.getJSONObject(j)
                files.add(ModelFile(f.getString("quant"), f.getString("path"), f.getLong("bytes")))
            }
            val caps = ArrayList<String>()
            m.optJSONArray("capabilities")?.let { for (j in 0 until it.length()) caps.add(it.getString(j)) }
            val kv = m.optJSONObject("kv")?.let {
                KvHint(it.getInt("layers"), it.getInt("kv_heads"), it.getInt("head_dim"))
            }
            out.add(
                Model(
                    id = m.getString("id"),
                    name = m.getString("name"),
                    vendor = m.optString("vendor", ""),
                    paramsB = if (m.isNull("params_b")) null else m.optDouble("params_b"),
                    activeParamsB = if (m.isNull("active_params_b")) null else m.optDouble("active_params_b"),
                    arch = m.optString("arch", "dense"),
                    license = m.optString("license", "see-model-card"),
                    licenseSource = m.optString("license_source", "unverified"),
                    capabilities = caps,
                    qualityTier = m.optInt("quality_tier", 3),
                    role = m.optString("role", "general"),
                    hfRepo = m.getString("hf_repo"),
                    kv = kv,
                    files = files,
                )
            )
        }
        return out
    }
}
