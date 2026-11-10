import DatasLink
import Foundation

/// The app's few sentences, in English and Spanish. English is the key; a sentence without
/// Spanish is shown in English.
enum Words {
    static let spanish = (Locale.preferredLanguages.first ?? "en").lowercased().hasPrefix("es")

    static let es: [String: String] = [
        "My computers": "Mis computadoras",
        "No computer is linked yet.": "Todavía no hay ninguna computadora vinculada.",
        "On your computer open Datas → Devices → Show a code. Then tap “Link a computer” here and type the address and the code it shows.":
            "En tu computadora abrí Datas → Dispositivos → Mostrar un código. Después tocá «Vincular una computadora» acá y escribí la dirección y el código que muestra.",
        "Link a computer": "Vincular una computadora",
        "Ready": "Lista",
        "Not reachable right now": "No se la puede alcanzar ahora",
        "Checking…": "Comprobando…",
        "The computer does the thinking: this phone shows its Datas over an encrypted link. Nothing is stored on the phone except how to reach your computers.":
            "La computadora es la que piensa: este teléfono muestra su Datas por un enlace cifrado. En el teléfono no se guarda nada, salvo cómo llegar a tus computadoras.",
        "Address, for example 192.168.1.20:8424": "Dirección, por ejemplo 192.168.1.20:8424",
        "The 12 letters and digits": "Las 12 letras y números",
        "Link": "Vincular",
        "Cancel": "Cancelar",
        "On your computer: Datas → Devices → Show a code. It shows an address and a code that works once, for ten minutes.":
            "En tu computadora: Datas → Dispositivos → Mostrar un código. Muestra una dirección y un código que sirve una sola vez, durante diez minutos.",
        "Seen on this network": "Vistas en esta red",
        "Looking for computers with Datas on this Wi-Fi…": "Buscando computadoras con Datas en este Wi-Fi…",
        "Type the address the computer shows.": "Escribí la dirección que muestra la computadora.",
        "Could not find the address of that computer. Type it as the computer shows it.":
            "No se pudo encontrar la dirección de esa computadora. Escribila como la muestra la computadora.",
        "Connecting…": "Conectando…",
        "Try again": "Probar de nuevo",
        "OK": "Aceptar",
        // what the link itself can say (DatasLink)
        "Could not reach that computer. Is Datas open on it, and is this phone on the same network?":
            "No se pudo llegar a esa computadora. ¿Datas está abierto ahí? ¿Este teléfono está en la misma red?",
        "The device at that address is not the computer that was linked.":
            "El dispositivo en esa dirección no es la computadora que se vinculó.",
        "The code has 12 letters and digits.": "El código tiene 12 letras y números.",
        "That computer is not showing a code right now.": "Esa computadora no está mostrando un código en este momento.",
        "Wrong or expired code.": "Código equivocado o vencido.",
        "The computer could not prove it knows the code. Nothing was linked.":
            "La computadora no pudo demostrar que conoce el código. No se vinculó nada.",
        "The computer refused.": "La computadora se negó.",
        "The computer did not answer in time.": "La computadora no respondió a tiempo.",
        "The connection to the computer was lost.": "Se perdió la conexión con la computadora.",
        "The computer sent something unexpected.": "La computadora envió algo inesperado.",
        "The computer sent something unexpected. Is its Datas up to date?":
            "La computadora envió algo inesperado. ¿Su Datas está actualizado?",
        "That address is not complete.": "Esa dirección no está completa.",
        "The computer did not identify itself.": "La computadora no se identificó.",
        "This phone lacks a needed security function (PBKDF2).": "A este teléfono le falta una función de seguridad necesaria (PBKDF2).",
        "This phone could not open its side of the connection.": "Este teléfono no pudo abrir su lado de la conexión.",
    ]

    static func t(_ english: String) -> String {
        spanish ? (es[english] ?? english) : english
    }

    /// A problem reported by the link, in the person's language. The technical reason some
    /// messages carry in brackets is left out: it helps nobody on a phone.
    static func problem(_ message: String) -> String {
        if message.hasPrefix(Channel.unreachable) { return t(Channel.unreachable) }
        return t(message)
    }
}

func T(_ english: String) -> String {
    Words.t(english)
}
