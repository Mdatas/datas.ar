package ar.datas.app

import kotlin.math.max

/**
 * Kotlin port of datas/recommend/engine.py, restricted to what a phone is: one pool of
 * unified memory, CPU/NPU inference. Same formulas, same thresholds, same ranking.
 */
object Recommender {
    private const val MIB = 1024L * 1024L
    private const val GIB = 1024L * MIB

    const val DEFAULT_HEADROOM = 0.40          // phones: Android kills hungry apps without warning
    const val HEADROOM_MIN_GIB = 2.0

    data class Budget(val ramTotal: Long, val ramBudget: Long, val ramHeadroom: Long, val diskFree: Long, val threads: Int)

    data class Need(val weights: Long, val kvCache: Long, val overhead: Long, val kvExact: Boolean, val context: Int) {
        val total: Long get() = weights + kvCache + overhead
    }

    data class Candidate(
        val model: Model,
        val file: ModelFile,
        val need: Need,
        val fits: Boolean,
        val fitLevel: String,      // comfortable | tight | none
        val speedClass: String,    // ok | slow | crawl  (phones never earn "fast")
        val margin: Long,
        val effectiveTier: Int,
        val activeBytes: Long,
    ) {
        val usable: Boolean get() = speedClass == "ok"
    }

    data class Recommendation(val budget: Budget, val context: Int, val default: Candidate?, val fits: List<Candidate>, val doesNotFit: List<Candidate>)

    fun budgetFor(d: DeviceInfo, headroom: Double = DEFAULT_HEADROOM): Budget {
        val head = max((HEADROOM_MIN_GIB * GIB).toLong(), (headroom * d.ramTotal).toLong())
        val threads = if (d.cores >= 4) d.cores - 1 else d.cores
        return Budget(d.ramTotal, max(0L, d.ramTotal - head), head, d.diskFree, max(1, threads))
    }

    private fun estimateLayers(paramsB: Double): Int = when {
        paramsB <= 2 -> 28
        paramsB <= 9 -> 36
        paramsB <= 15 -> 48
        paramsB <= 35 -> 64
        paramsB <= 80 -> 80
        else -> 96
    }

    private fun kvHint(m: Model, f: ModelFile): Pair<KvHint, Boolean> =
        m.kv?.let { it to true } ?: (KvHint(estimateLayers(m.paramsEstimate(f)), 8, 128) to false)

    fun need(m: Model, f: ModelFile, context: Int, kvBits: Int = 16): Need {
        val (hint, exact) = kvHint(m, f)
        val overhead = (0.08 * f.bytes).toLong() + 512 * MIB
        return Need(f.bytes, hint.bytesPerToken(kvBits) * context, overhead, exact, context)
    }

    private fun comfortableMargin(budget: Long): Long = max(512 * MIB, (0.10 * budget).toLong())

    // iGPU / phone unified memory: DDR-class bandwidth. "ok" ≈ readable chat pace.
    private fun speedClass(activeBytes: Long): String {
        val a = activeBytes.toDouble() / GIB
        return if (a <= 3.5) "ok" else if (a <= 7) "slow" else "crawl"
    }

    fun evaluate(m: Model, f: ModelFile, b: Budget, context: Int, kvBits: Int = 16): Candidate {
        val n = need(m, f, context, kvBits)
        val total = m.paramsEstimate(f)
        val active = m.activeEstimate(f)
        val activeBytes = if (total > 0) (n.weights * (active / total)).toLong() else n.weights
        val fits = n.total <= b.ramBudget && f.bytes + GIB <= b.diskFree
        val margin = b.ramBudget - n.total
        val fitLevel = if (!fits) "none" else if (margin >= comfortableMargin(b.ramBudget)) "comfortable" else "tight"
        val speed = if (fits) speedClass(activeBytes) else "crawl"
        val tier = m.qualityTier - if (Catalog.bitsPerWeight(f.quant) < 3.6) 1 else 0
        return Candidate(m, f, n, fits, fitLevel, speed, margin, tier, activeBytes)
    }

    private fun rankKey(c: Candidate): List<Long> = listOf(
        if (c.usable) 0L else 1L,
        -c.effectiveTier.toLong(),
        when (c.speedClass) { "ok" -> 0L; "slow" -> 1L; else -> 2L },
        if (c.fitLevel == "comfortable") 0L else 1L,
        -c.need.weights,
    )

    private fun compare(a: Candidate, b: Candidate): Int {
        val ka = rankKey(a); val kb = rankKey(b)
        for (i in ka.indices) { val d = ka[i].compareTo(kb[i]); if (d != 0) return d }
        return 0
    }

    fun recommend(models: List<Model>, d: DeviceInfo, headroom: Double = DEFAULT_HEADROOM, context: Int = 4096, kvBits: Int = 16): Recommendation {
        val b = budgetFor(d, headroom)
        val all = models.flatMap { m -> m.files.map { f -> evaluate(m, f, b, context, kvBits) } }
        val fits = all.filter { it.fits }.sortedWith { x, y -> compare(x, y) }
        val noFit = all.filter { !it.fits }.sortedBy { it.need.total }

        val generals = fits.filter { it.model.role == "general" }
        var pick = generals.firstOrNull { it.fitLevel == "comfortable" && it.usable }
            ?: generals.firstOrNull { it.usable } ?: generals.firstOrNull() ?: fits.firstOrNull()
        if (pick != null) {
            // within the chosen model: quality, then speed, then the largest comfortable quant
            val same = fits.filter { it.model.id == pick!!.model.id }
            val good = same.filter { it.fitLevel == "comfortable" && it.usable }.ifEmpty { same }
            pick = good.sortedWith(compareBy<Candidate>({ -it.effectiveTier }, { if (it.usable) 0 else 1 }, { -it.need.weights })).first()
        }
        // one row per model for display
        val seen = HashSet<String>()
        val fitsDedup = fits.filter { seen.add(it.model.id) }
        val seen2 = HashSet<String>(seen)
        val noFitDedup = noFit.filter { seen2.add(it.model.id) }
        return Recommendation(b, context, pick, fitsDedup, noFitDedup)
    }
}
