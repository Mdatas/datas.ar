package ar.datas.app

import android.content.Context
import ar.datas.link.LinkClient

/**
 * The computers this phone is linked to. Kept in the app's private storage, which other apps
 * cannot read; each entry holds the computer's certificate fingerprint and this phone's
 * secret for it (see ar.datas.link.LinkClient).
 */
object Computers {
    private const val PREFS = "computers"
    private const val KEY = "list"

    fun all(ctx: Context): List<LinkClient.Computer> {
        val raw = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getStringSet(KEY, null) ?: emptySet()
        val out = ArrayList<LinkClient.Computer>()
        for (text in raw) {
            try {
                out.add(LinkClient.Computer.fromJson(text))
            } catch (e: RuntimeException) {
                // an entry that cannot be read is left out
            }
        }
        out.sortBy { it.name.lowercase() }
        return out
    }

    fun find(ctx: Context, id: String): LinkClient.Computer? = all(ctx).firstOrNull { it.id == id }

    fun save(ctx: Context, computer: LinkClient.Computer) {
        val keep = all(ctx).filter { it.id != computer.id } + computer
        store(ctx, keep)
    }

    fun forget(ctx: Context, id: String) {
        store(ctx, all(ctx).filter { it.id != id })
    }

    private fun store(ctx: Context, list: List<LinkClient.Computer>) {
        val set = HashSet<String>()
        for (c in list) set.add(c.toJson())
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putStringSet(KEY, set).apply()
    }
}
