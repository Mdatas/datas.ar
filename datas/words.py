"""The sentences Datas itself says, in the person's language.

The window has its own word list (datas/server/ui/i18n.js). This file is for what the
*backend* says: why a camera could not be used, what a printer answered, why a request was
refused. English is the source — the English sentence is the key — and ``ES`` holds the
Spanish for each. A sentence that has no Spanish yet is simply shown in English.

A sentence is kept apart from its values (``"There is no printer called {name}."`` and
``name="HP"``) so that it can be said again in another language:

* ``Problem``  an error to show to the person (``ThingError`` and others build on it)
* ``Said``     a sentence that reports what was done; it behaves like a plain string
* ``tr``       say a sentence in a language

Words follow the window's Spanish: Rioplatense "vos", "computadora", "IA", "aparatos".
tests/test_words.py checks that every sentence of the hardware layer has its Spanish and that
both versions name the same values.
"""

from __future__ import annotations

LANGS = ("en", "es")


def _fmt(text: str, values: dict) -> str:
    if not values:
        return text
    try:
        return text.format_map(values)
    except (KeyError, IndexError, ValueError):
        return text


def tr(text: str, lang: str = "en", /, **values) -> str:  # noqa: ANN003
    """``text`` in ``lang`` with its values filled in. A value that is itself a sentence
    (a ``Problem``, a ``Said`` or a plain sentence that has a translation) is translated too."""
    spanish = lang == "es"
    out = {}
    for k, v in values.items():
        if hasattr(v, "say"):
            v = v.say(lang)
        elif isinstance(v, BaseException):
            v = str(v)
        elif spanish and isinstance(v, str):
            v = ES.get(v, v)
        out[k] = v
    return _fmt(ES.get(text, text) if spanish else text, out)


class Problem(RuntimeError):
    """Something to tell the person in plain words. ``str(problem)`` is the English;
    ``problem.say("es")`` the same in Spanish."""

    def __init__(self, text: str, /, **values) -> None:  # noqa: ANN003
        self.text, self.values = text, values
        super().__init__(tr(text, "en", **values))

    def say(self, lang: str = "en") -> str:
        return tr(self.text, lang, **self.values)


class Said(str):
    """A sentence that reports what happened. It is a normal string (the English), and
    ``.say("es")`` gives the Spanish."""

    text: str
    values: dict

    def __new__(cls, text: str, /, **values):  # noqa: ANN003, ANN204
        obj = super().__new__(cls, tr(text, "en", **values))
        obj.text, obj.values = text, values
        return obj

    def say(self, lang: str = "en") -> str:
        return tr(self.text, lang, **self.values)


def say(thing, lang: str = "en") -> str:  # noqa: ANN001
    """Any message in ``lang``: a Problem or Said says itself, a known plain sentence is
    looked up, anything else comes back as it is."""
    if hasattr(thing, "say"):
        return thing.say(lang)
    return tr(str(thing), lang)


# ---------------------------------------------------------------------------
# Spanish
# ---------------------------------------------------------------------------

ES: dict[str, str] = {
    # ---- hardware: cameras, the screen (datas/things/local.py) ---------------------------
    "The camera needs FFmpeg, a free program that is not on this computer yet. Get it once "
    "under Tools → Cameras, printers and other hardware.": "La cámara necesita FFmpeg, un "
    "programa libre que todavía no está en esta computadora. Bajalo una sola vez en "
    "Herramientas → Cámaras, impresoras y otros aparatos.",
    "The camera needs FFmpeg. {why}": "La cámara necesita FFmpeg. {why}",
    "No camera was found on this computer.": "No se encontró ninguna cámara en esta computadora.",
    "There is no camera called {name}. Found: {names}": "No hay ninguna cámara llamada "
    "{name}. Encontradas: {names}",
    "The camera did not answer in time. Is another program using it?": "La cámara no "
    "respondió a tiempo. ¿La está usando otro programa?",
    "Could not take a picture. The camera may be in use by another program, or this system "
    "did not allow Datas to use it. ({why})": "No se pudo sacar la foto. Puede que otro "
    "programa esté usando la cámara, o que el sistema no le haya permitido a Datas usarla. "
    "({why})",
    "no picture came out": "no salió ninguna imagen",
    "Datas could not look at the screen on this system. On Linux this needs an X11 session "
    "or the program gnome-screenshot; on macOS, allow Datas under Privacy → Screen "
    "Recording. ({why})": "Datas no pudo mirar la pantalla en este sistema. En Linux hace "
    "falta una sesión X11 o el programa gnome-screenshot; en macOS, permitile a Datas en "
    "Privacidad → Grabación de pantalla. ({why})",
    # ---- hardware: printers ---------------------------------------------------------------
    "There is no file {name} to print.": "No hay ningún archivo {name} para imprimir.",
    "No printer is set up on this computer.": "No hay ninguna impresora configurada en esta "
    "computadora.",
    "There is no printer called {name}. Found: {names}": "No hay ninguna impresora llamada "
    "{name}. Encontradas: {names}",
    "LibreOffice could not print it: {why}": "LibreOffice no pudo imprimirlo: {why}",
    "Without LibreOffice, Datas can only print to the default printer on Windows. Install "
    "LibreOffice (free) or make that printer the default.": "Sin LibreOffice, en Windows "
    "Datas solo puede imprimir en la impresora predeterminada. Instalá LibreOffice (libre y "
    "gratis) o poné esa impresora como predeterminada.",
    "Windows has no program that can print this kind of file by itself. Install LibreOffice "
    "(free) and try again.": "Windows no tiene un programa que imprima solo este tipo de "
    "archivo. Instalá LibreOffice (libre y gratis) y probá de nuevo.",
    "This system has no printing service (CUPS).": "Este sistema no tiene servicio de "
    "impresión (CUPS).",
    "A {kind} file has to become a PDF before it can be printed, and that needs LibreOffice "
    "(free). Save it as PDF, or install LibreOffice.": "Un archivo {kind} tiene que "
    "convertirse en PDF antes de imprimirse, y para eso hace falta LibreOffice (libre y "
    "gratis). Guardalo como PDF, o instalá LibreOffice.",
    "LibreOffice could not turn that file into a PDF to print it.": "LibreOffice no pudo "
    "convertir ese archivo en PDF para imprimirlo.",
    "The printer did not take it: {why}": "La impresora no lo aceptó: {why}",
    "that printer cannot be used": "esa impresora no se puede usar",
    "no answer": "sin respuesta",
    "Sent {name} to the printer {printer}.": "Se envió {name} a la impresora {printer}.",
    "Sent {name} to the printer {printer}, {copies} copies.": "Se envió {name} a la "
    "impresora {printer}, {copies} copias.",
    "Asked Windows to print {name} on the default printer.": "Se le pidió a Windows que "
    "imprima {name} en la impresora predeterminada.",
    # ---- hardware: boards on serial ports -------------------------------------------------
    "The serial-port part (pyserial) is missing from this copy of Datas.": "A esta copia de "
    "Datas le falta la parte de los puertos serie (pyserial).",
    "Could not use {port}: {why}. Is the board plugged in, and is another program (the "
    "Arduino program's serial monitor, for example) using it?": "No se pudo usar {port}: "
    "{why}. ¿Está enchufada la placa? ¿La está usando otro programa (por ejemplo, el "
    "monitor serie del programa de Arduino)?",
    "Arduino board": "placa Arduino",
    "board with a CH340 USB chip (many Arduino-compatible and ESP boards)": "placa con chip "
    "USB CH340 (muchas placas compatibles con Arduino y ESP)",
    "board with a CP210x USB chip (many ESP32 boards)": "placa con chip USB CP210x (muchas "
    "placas ESP32)",
    "FTDI USB-serial adapter": "adaptador USB-serie FTDI",
    "Espressif board (ESP32)": "placa Espressif (ESP32)",
    "Raspberry Pi Pico": "Raspberry Pi Pico",
    "STMicroelectronics board": "placa STMicroelectronics",
    "Teensy or a similar board": "Teensy o una placa parecida",
    "micro:bit or an Arm Mbed board": "micro:bit o una placa Arm Mbed",
    "Adafruit board": "placa Adafruit",
    "SparkFun board": "placa SparkFun",
    "serial device": "aparato serie",
    # ---- hardware: the mouse and keyboard (datas/things/control.py) -----------------------
    "Mouse and keyboard control is not available: {why}.": "El control del mouse y el "
    "teclado no está disponible: {why}.",
    "this session uses Wayland; mouse and keyboard control needs X11": "esta sesión usa "
    "Wayland; el control del mouse y el teclado necesita X11",
    "there is no screen session": "no hay una sesión con pantalla",
    "the mouse and keyboard part (PyAutoGUI) is not in this copy": "esta copia no trae la "
    "parte del mouse y el teclado (PyAutoGUI)",
    "Mouse and keyboard control could not start: {why}": "El control del mouse y el teclado "
    "no pudo arrancar: {why}",
    "action is one of: {actions}": "action es una de: {actions}",
    "That needs a place on the screen: x and y.": "Eso necesita un lugar en la pantalla: x e y.",
    "({x}, {y}) is outside the picture of the screen, which is {w} by {h}.": "({x}, {y}) "
    "queda fuera de la imagen de la pantalla, que mide {w} por {h}.",
    "Nothing to type.": "No hay nada para escribir.",
    'Name the key, for example "enter" or "ctrl+s".': 'Nombrá la tecla, por ejemplo "enter" '
    'o "ctrl+s".',
    "Stopped: the mouse was moved into a corner of the screen.": "Detenido: el mouse se "
    "movió a una esquina de la pantalla.",
    "The system did not allow that: {why}": "El sistema no lo permitió: {why}",
    "Click at ({x}, {y})": "Clic en ({x}, {y})",
    "Double-click at ({x}, {y})": "Doble clic en ({x}, {y})",
    "Right-click at ({x}, {y})": "Clic derecho en ({x}, {y})",
    "Move the mouse to ({x}, {y})": "Mover el mouse a ({x}, {y})",
    "Type: {text}": "Escribir: {text}",
    "Press {keys}": "Apretar {keys}",
    "Scroll up {n}": "Desplazar hacia arriba {n}",
    "Scroll down {n}": "Desplazar hacia abajo {n}",
    "Done: {what}": "Hecho: {what}",
    # ---- what the agent asks before using a device ----------------------------------------
    "Mouse and keyboard — {what}": "Mouse y teclado — {what}",
    "Take a picture with the camera": "Sacar una foto con la cámara",
    "Take a picture with the camera {camera}": "Sacar una foto con la cámara {camera}",
    "Take a picture of what is on your screen": "Sacar una imagen de lo que hay en tu pantalla",
    "Print {name} on paper": "Imprimir {name} en papel",
    "Print {name} on paper ({copies} copies)": "Imprimir {name} en papel ({copies} copias)",
    "Write to the board on {port}: {text}": "Escribirle a la placa en {port}: {text}",
    "Send to {topic} (MQTT): {message}": "Enviar a {topic} (MQTT): {message}",
    "Ask Home Assistant to do {service}": "Pedirle a Home Assistant que haga {service}",
    "Ask Home Assistant to do {service} on {entity}": "Pedirle a Home Assistant que haga "
    "{service} en {entity}",
    "Write {values} at address {address} of {device} (Modbus)": "Escribir {values} en la "
    "dirección {address} de {device} (Modbus)",
    # ---- hardware on the network: MQTT, Home Assistant, Modbus (datas/things/net.py) ------
    "No MQTT broker is set up. Add its address under Tools → Cameras, printers and other "
    "hardware → Home and industrial devices.": "No hay ningún broker MQTT configurado. "
    "Agregá su dirección en Herramientas → Cámaras, impresoras y otros aparatos → Aparatos "
    "del hogar y de la industria.",
    "The MQTT part (paho-mqtt) is missing from this copy of Datas.": "A esta copia de Datas "
    "le falta la parte de MQTT (paho-mqtt).",
    "Could not reach the MQTT broker at {host}: {why}": "No se pudo llegar al broker MQTT en "
    "{host}: {why}",
    "The MQTT broker did not accept the connection (wrong user or password?).": "El broker "
    "MQTT no aceptó la conexión (¿usuario o contraseña equivocados?).",
    "To send, name one exact topic (no # or +).": "Para enviar, nombrá un tema exacto (sin # "
    "ni +).",
    "The broker did not confirm the message.": "El broker no confirmó el mensaje.",
    "Sent to {topic}.": "Enviado a {topic}.",
    "Home Assistant is not set up. Add its address and a long-lived access token (Home "
    "Assistant → your profile → Security) under Tools → Cameras, printers and other hardware "
    "→ Home and industrial devices.": "Home Assistant no está configurado. Agregá su "
    "dirección y un token de acceso de larga duración (Home Assistant → tu perfil → "
    "Seguridad) en Herramientas → Cámaras, impresoras y otros aparatos → Aparatos del hogar "
    "y de la industria.",
    "Home Assistant refused the access token. Make a new one and save it again.": "Home "
    "Assistant rechazó el token de acceso. Creá uno nuevo y guardalo otra vez.",
    "Home Assistant answered with an error ({code}): {text}": "Home Assistant respondió con "
    "un error ({code}): {text}",
    "Could not reach Home Assistant: {why}": "No se pudo llegar a Home Assistant: {why}",
    'A service looks like "light.turn_on".': 'Un servicio se escribe así: "light.turn_on".',
    "Home Assistant did {service}.": "Home Assistant hizo {service}.",
    "Home Assistant did {service} on {entity}.": "Home Assistant hizo {service} en {entity}.",
    "There is no Modbus device called {name}. Set up: {names}": "No hay ningún aparato "
    "Modbus llamado {name}. Configurados: {names}",
    "There is no Modbus device called {name}. None is set up yet (Tools → Cameras, printers "
    "and other hardware).": "No hay ningún aparato Modbus llamado {name}. Todavía no hay "
    "ninguno configurado (Herramientas → Cámaras, impresoras y otros aparatos).",
    "The device answered with something that is not Modbus.": "El aparato respondió con algo "
    "que no es Modbus.",
    "Could not reach the device at {host}:{port}: {why}": "No se pudo llegar al aparato en "
    "{host}:{port}: {why}",
    "The device refused: {why}.": "El aparato se negó: {why}.",
    "the device does not know that kind of request": "el aparato no conoce ese tipo de pedido",
    "there is nothing at that address in the device": "no hay nada en esa dirección del aparato",
    "the device does not accept that value": "el aparato no acepta ese valor",
    "the device failed while doing it": "el aparato falló al hacerlo",
    "the device is busy": "el aparato está ocupado",
    "error {code}": "error {code}",
    "The device answered a different question than the one asked.": "El aparato respondió a "
    "otra pregunta, no a la que se le hizo.",
    "kind is one of: holding, input, coil, discrete.": "kind es uno de: holding, input, "
    "coil, discrete.",
    "Ask for 1 to {top} values, at an address from 0 to 65535.": "Pedí de 1 a {top} valores, "
    "en una dirección de 0 a 65535.",
    "The device sent fewer values than asked.": "El aparato envió menos valores de los pedidos.",
    "Only holding registers and coils can be written; give at least one value.": "Solo se "
    "pueden escribir registros holding y coils; da al menos un valor.",
    "A holding register takes a whole number from 0 to 65535.": "Un registro holding acepta "
    "un número entero de 0 a 65535.",
    "Wrote {n} value(s) at {address} on {name}.": "Se escribieron {n} valor(es) en {address} "
    "de {name}.",
    "Check one of: mqtt, home_assistant, modbus.": "Probá uno de: mqtt, home_assistant, modbus.",
    "The MQTT broker accepted the connection.": "El broker MQTT aceptó la conexión.",
    "Home Assistant answered: it knows {n} things.": "Home Assistant respondió: conoce {n} cosas.",
    "{name} answers (it has nothing at address 0, which is normal).": "{name} responde (no "
    "tiene nada en la dirección 0, lo cual es normal).",
    "{name} answers; the value at address 0 is {value}.": "{name} responde; el valor en la "
    "dirección 0 es {value}.",
    # ---- what a device on the network says it is ------------------------------------------
    "printer": "impresora",
    "scanner": "escáner",
    "shared folders (a NAS or a computer)": "carpetas compartidas (un NAS o una computadora)",
    "shared folders (a NAS or a Mac)": "carpetas compartidas (un NAS o una Mac)",
    "shared folders (NFS)": "carpetas compartidas (NFS)",
    "computer that accepts remote log-in (SSH), such as a Raspberry Pi": "computadora que "
    "acepta ingreso remoto (SSH), como una Raspberry Pi",
    "computer that accepts file transfer (SFTP)": "computadora que acepta transferencia de "
    "archivos (SFTP)",
    "computer": "computadora",
    "Home Assistant": "Home Assistant",
    "smart-home device (HomeKit)": "aparato de casa inteligente (HomeKit)",
    "smart-home device (Matter)": "aparato de casa inteligente (Matter)",
    "ESPHome board": "placa ESPHome",
    "MQTT broker": "broker MQTT",
    "Chromecast or a screen with Google Cast": "Chromecast o una pantalla con Google Cast",
    "screen or speaker with AirPlay": "pantalla o parlante con AirPlay",
    "speaker with AirPlay": "parlante con AirPlay",
    "speaker": "parlante",
    "camera or video stream": "cámara o transmisión de video",
    "3D printer (OctoPrint)": "impresora 3D (OctoPrint)",
    "computer with Datas": "computadora con Datas",
    "device with a web page": "aparato con una página web",
    "device that announces itself (UPnP)": "aparato que se anuncia (UPnP)",
    # ---- FFmpeg, fetched once (datas/programs.py) -----------------------------------------
    "There is no ready-made FFmpeg for this kind of computer. Install it from "
    "https://ffmpeg.org (or with your system's package manager).": "No hay un FFmpeg listo "
    "para este tipo de computadora. Instalalo desde https://ffmpeg.org (o con el gestor de "
    "paquetes de tu sistema).",
    "The FFmpeg file that arrived is not the one Datas expects, so it was not used. Try "
    "again later, or install FFmpeg from https://ffmpeg.org.": "El archivo de FFmpeg que "
    "llegó no es el que Datas espera, así que no se usó. Probá de nuevo más tarde, o "
    "instalá FFmpeg desde https://ffmpeg.org.",
    "FFmpeg could not be downloaded ({why}). Check the connection and try again, or install "
    "FFmpeg from https://ffmpeg.org.": "No se pudo bajar FFmpeg ({why}). Revisá la conexión "
    "y probá de nuevo, o instalá FFmpeg desde https://ffmpeg.org.",
    "FFmpeg arrived but could not be unpacked: {why}": "FFmpeg llegó pero no se pudo "
    "desempaquetar: {why}",
    "The FFmpeg download did not contain the program.": "La descarga de FFmpeg no traía el "
    "programa.",
    "Getting FFmpeg, the free program that reads cameras and recordings…": "Bajando FFmpeg, "
    "el programa libre que lee cámaras y grabaciones…",
    # ---- the local service: who may ask for what (datas/server/app.py) --------------------
    "This can only be done at the computer itself, not from a linked phone.": "Esto solo se "
    "puede hacer en la computadora misma, no desde un teléfono vinculado.",
    "This address is not one Datas answers to (see docs/SECURITY.md).": "Datas no responde "
    "en esta dirección (ver docs/SECURITY.md).",
    "Requests from other web pages are not accepted.": "No se aceptan pedidos de otras "
    "páginas web.",
    "From a linked phone the agent cannot run commands or use the computer's devices. Switch "
    "those on at the computer itself.": "Desde un teléfono vinculado el agente no puede "
    "ejecutar comandos ni usar los aparatos de la computadora. Activá eso en la computadora "
    "misma.",
    "From a linked phone, a task that runs by itself cannot be given commands or the "
    "computer's devices, and one that has them cannot be changed. Do that at the computer.": ""
    "Desde un teléfono vinculado no se le pueden dar comandos ni los aparatos de la "
    "computadora a una tarea que corre sola, y una que ya los tiene no se puede cambiar. "
    "Hacelo en la computadora.",
    "There is nothing to print.": "No hay nada para imprimir.",
    "That could not be saved: {why}": "Eso no se pudo guardar: {why}",
    "No AI is running yet.": "Todavía no hay ninguna IA en marcha.",
}
