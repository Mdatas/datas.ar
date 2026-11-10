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
    # ---- starting with the computer (datas/service.py) ------------------------------------
    "Starting Datas with the computer is available on Linux, Windows and macOS. Start it "
    "yourself with: datas-cli serve --no-browser": "Que Datas arranque con la computadora "
    "está disponible en Linux, Windows y macOS. Arrancalo vos con: datas-cli serve --no-browser",
    "This system has no systemd, the part of Linux that Datas uses to start with the "
    "computer. Start it yourself with: datas-cli serve --no-browser": "Este sistema no "
    "tiene systemd, la parte de Linux que Datas usa para arrancar con la computadora. "
    "Arrancalo vos con: datas-cli serve --no-browser",
    # ---- the local service: who may ask for what (datas/server/app.py) --------------------
    "This can only be done at the computer itself, not from a linked device.": "Esto solo se "
    "puede hacer en la computadora misma, no desde un dispositivo vinculado.",
    "This address is not one Datas answers to (see docs/SECURITY.md).": "Datas no responde "
    "en esta dirección (ver docs/SECURITY.md).",
    "Requests from other web pages are not accepted.": "No se aceptan pedidos de otras "
    "páginas web.",
    "From a linked device the agent cannot run commands or use the computer's devices. Switch "
    "those on at the computer itself.": "Desde un dispositivo vinculado el agente no puede "
    "ejecutar comandos ni usar los aparatos de la computadora. Activá eso en la computadora "
    "misma.",
    "From a linked device, a task that runs by itself cannot be given commands or the "
    "computer's devices, and one that has them cannot be changed. Do that at the computer.": ""
    "Desde un dispositivo vinculado no se le pueden dar comandos ni los aparatos de la "
    "computadora a una tarea que corre sola, y una que ya los tiene no se puede cambiar. "
    "Hacelo en la computadora.",
    "There is nothing to print.": "No hay nada para imprimir.",
    "That could not be saved: {why}": "Eso no se pudo guardar: {why}",
    "No AI is running yet.": "Todavía no hay ninguna IA en marcha.",
    # ---- short answers of the local service ------------------------------------------------
    "no such file": "no existe ese archivo",
    "nothing to say": "no hay nada para decir",
    "no such job": "no existe ese trabajo",
    "reserved name": "ese nombre está reservado",
    "unknown provider": "servicio desconocido",
    "Give an audio or video file (mp3, wav, m4a, mp4, mkv…).": "Dame un archivo de audio o de "
    "video (mp3, wav, m4a, mp4, mkv…).",
    "The file arrived empty.": "El archivo llegó vacío.",
    "There is no text to work on.": "No hay texto con el que trabajar.",
    "mode must be summary or translate": "el modo tiene que ser summary o translate",
    "no such connection": "no existe esa conexión",
    "Could not find the newest engine version (no connection?)": "No se pudo encontrar la "
    "versión más nueva del motor (¿no hay conexión?)",
    "which version?": "¿qué versión?",
    "that device is not linked": "ese dispositivo no está vinculado",
    "not installed": "no está instalado",
    "no such chat": "no existe ese chat",
    "memory is off (forget mode)": "la memoria está apagada (modo Olvidar)",
    "no such helper": "no existe ese ayudante",
    "no such lesson": "no existe esa lección",
    "no such lesson or link": "no existe esa lección ni ese enlace",
    "only web addresses can be opened": "solo se pueden abrir direcciones web",
    "no such question (it may have timed out)": "no existe esa pregunta (puede que haya vencido)",
    "no such task": "no existe esa tarea",
    "no such task, or another task is running": "no existe esa tarea, o hay otra tarea en marcha",
    "no such app": "no existe esa aplicación",
    "the file did not arrive whole; try again": "el archivo no llegó entero; probá de nuevo",
    "bad request body": "el pedido llegó mal formado",
    # ---- a recommendation in plain words (datas/recommend/engine.py) ------------------------
    "Fast — answers appear quickly, like a paid chat service.": "Rápida — las respuestas aparecen enseguida, como en un servicio de chat pago.",
    "Comfortable — a readable pace, a few words per second.": "Cómoda — un ritmo que se puede leer, algunas palabras por segundo.",
    "Slow — expect to wait; fine for short questions.": "Lenta — vas a tener que esperar; sirve para preguntas cortas.",
    "Very slow — only if nothing else fits.": "Muy lenta — solo si no entra ninguna otra.",
    "Runs on your graphics card (GPU, the chip that normally draws games and video).": "Corre en tu placa de video (GPU, el chip que normalmente dibuja los juegos y el video).",
    "Runs partly on your graphics card (GPU) and partly in main memory (RAM).": "Corre una parte en tu placa de video (GPU) y otra parte en la memoria principal (RAM).",
    "Runs on your processor (CPU) using main memory (RAM).": "Corre en tu procesador (CPU) usando la memoria principal (RAM).",
    "Runs in your device's shared memory (used by both the processor and graphics).": "Corre en la memoria compartida de tu dispositivo (la usan el procesador y los gráficos).",
    "Runs spread across your devices on the home network.": "Corre repartida entre tus dispositivos de la red de tu casa.",
    "Does not fit in this device's memory.": "No entra en la memoria de este dispositivo.",
    "{size} GB to download once; then it works offline.": "{size} GB para descargar una sola vez; después funciona sin conexión.",
    "Uses about {size} GB of memory while running.": "Usa unos {size} GB de memoria mientras está en marcha.",
    " (license not yet verified by Datas)": " (licencia todavía no verificada por Datas)",
    "Mixture of Experts (MoE): only a slice of the model works on each word, so it is faster than its size suggests.": "Mezcla de Expertos (MoE, por sus siglas en inglés): solo una parte del modelo trabaja en cada palabra, por eso es más rápida de lo que su tamaño hace pensar.",
    "Dense model: the whole model works on every word.": "Modelo denso: todo el modelo trabaja en cada palabra.",
    "A model file you added yourself.": "Un archivo de modelo que agregaste vos.",
    # ---- which paid AI it is like (datas/catalog/compare.py) ---------------------------------
    "Rough comparison by capability class, chosen by the Datas team — not a benchmark. The paid models also have internet search, bigger memories and the latest news built in.": "Comparación aproximada por nivel de capacidad, elegida por el equipo de Datas; no es una medición. Los modelos pagos además traen búsqueda en internet, memorias más grandes y las últimas noticias.",
    "below GPT-5.4 Nano": "por debajo de GPT-5.4 Nano",
    "below Gemini 3.5 Flash-Lite": "por debajo de Gemini 3.5 Flash-Lite",
    "below Claude Haiku 5.5": "por debajo de Claude Haiku 5.5",
    "approaching GPT-5.4 Nano": "cerca de GPT-5.4 Nano",
    "approaching Gemini 3.5 Flash-Lite": "cerca de Gemini 3.5 Flash-Lite",
    "approaching Claude Haiku 5.5": "cerca de Claude Haiku 5.5",
    "GPT-5.4 Nano class": "del nivel de GPT-5.4 Nano",
    "Gemini 3.5 Flash-Lite class": "del nivel de Gemini 3.5 Flash-Lite",
    "Claude Haiku 5.5 class": "del nivel de Claude Haiku 5.5",
    "GPT-5.4 Mini class": "del nivel de GPT-5.4 Mini",
    "Gemini 3.5 Flash class": "del nivel de Gemini 3.5 Flash",
    "between Claude Haiku 5.5 and Sonnet 5.5": "entre Claude Haiku 5.5 y Sonnet 5.5",
    "GPT-5.4 Mini to GPT-5.4 class": "entre el nivel de GPT-5.4 Mini y el de GPT-5.4",
    "Claude Sonnet 5.5 class": "del nivel de Claude Sonnet 5.5",
    "Much simpler than any paid AI — good for quick, short help on a very small device.": "Mucho más simple que cualquier IA paga: sirve para ayudas rápidas y cortas en un dispositivo muy chico.",
    "Handles everyday questions and short texts; the paid entry-level models are still noticeably better.": "Resuelve preguntas de todos los días y textos cortos; los modelos pagos más básicos siguen siendo claramente mejores.",
    "About the level of the cheapest paid tiers: good everyday assistant, verify facts.": "Más o menos el nivel de los planes pagos más baratos: buen asistente para todos los días; verificá los datos.",
    "Comparable to the mid-tier paid models most people actually use day to day.": "Comparable con los modelos pagos de nivel medio que la mayoría de la gente usa todos los días.",
    "Close to the mainstream paid models; the flagship paid models (GPT-5.5, Gemini 3.1 Pro, Claude Opus 5.5) remain stronger.": "Cerca de los modelos pagos más usados; los modelos pagos de punta (GPT-5.5, Gemini 3.1 Pro, Claude Opus 5.5) siguen siendo más fuertes.",
    # ---- what to keep in mind about each AI of the list (datas/catalog/models.json) ----------
    "Very small: fine for short answers, rewording and simple questions; makes mistakes on facts and anything long.": "Muy chica: sirve para respuestas cortas, reescribir frases y preguntas simples; se equivoca con los datos y con cualquier cosa larga.",
    "Very small: fine for short answers and simple rewording; weak on facts, math and long texts.": "Muy chica: sirve para respuestas cortas y para reescribir frases simples; floja con los datos, la matemática y los textos largos.",
    "Small: good everyday chat and can look at pictures; keep tasks short and double-check facts.": "Chica: buen chat para todos los días y puede mirar imágenes; pedile tareas cortas y revisá los datos.",
    "Small: good for short texts and simple step-by-step thinking; not reliable on facts or long documents.": "Chica: buena para textos cortos y razonamientos simples paso a paso; no es confiable con los datos ni con documentos largos.",
    "Small: decent writing help and simple tool use; limited knowledge, keep documents short.": "Chica: ayuda decente para escribir y uso simple de herramientas; sabe poco, dale documentos cortos.",
    "Capable for its size: writing, summaries, basic code and step-by-step reasoning; still invents facts sometimes.": "Capaz para su tamaño: escritura, resúmenes, código básico y razonamiento paso a paso; a veces todavía inventa datos.",
    "Good everyday assistant that also understands pictures; slower on long documents; verify facts.": "Buen asistente para todos los días que además entiende imágenes; más lento con documentos largos; verificá los datos.",
    "Strong at reasoning and short code for its size; smaller general knowledge, English-centric.": "Fuerte para razonar y para código corto, para su tamaño; menos conocimiento general y pensada sobre todo para inglés.",
    "Solid all-rounder: writing, summaries, code, reasoning; occasional factual slips on niche topics.": "Sirve bien para todo: escritura, resúmenes, código, razonamiento; cada tanto se equivoca con datos de temas poco comunes.",
    "Reasoning-focused with image understanding; answers can be long and slow; verify facts.": "Pensada para razonar y entiende imágenes; las respuestas pueden ser largas y lentas; verificá los datos.",
    "Strong assistant with image understanding; needs a mid-range computer; good multilingual quality.": "Asistente fuerte que entiende imágenes; necesita una computadora de gama media; buena calidad en varios idiomas.",
    "Strong reasoning, tool use and code; text only (no pictures); fast for its size because it is a Mixture of Experts (MoE).": "Fuerte para razonar, usar herramientas y programar; solo texto (sin imágenes); rápida para su tamaño porque es una Mezcla de Expertos (MoE).",
    "Strong writing, code and reasoning; text only; needs 10+ GB of memory.": "Fuerte para escribir, programar y razonar; solo texto; necesita 10 GB de memoria o más.",
    "Near-frontier quality with pictures; MoE design keeps it fast; needs 16+ GB of memory.": "Calidad cercana a la de los mejores modelos, con imágenes; el diseño MoE la mantiene rápida; necesita 16 GB de memoria o más.",
    "Top-tier open model with pictures, tools and reasoning; needs 20+ GB of memory and a good GPU for speed.": "Modelo abierto de primer nivel con imágenes, herramientas y razonamiento; necesita 20 GB de memoria o más y una buena placa de video (GPU) para ir rápido.",
    "Top-tier quality, fast thanks to MoE; pictures and tools; needs 22+ GB of memory.": "Calidad de primer nivel, rápida gracias al diseño MoE; imágenes y herramientas; necesita 22 GB de memoria o más.",
    "Top-tier reasoning and agent work, fast (MoE); text only; needs 20+ GB of memory.": "Razonamiento y trabajo de agente de primer nivel, rápida (MoE); solo texto; necesita 20 GB de memoria o más.",
    "Top-tier dense model with pictures; slower than MoE models of the same quality; needs 20+ GB and a GPU.": "Modelo denso de primer nivel con imágenes; más lento que los modelos MoE de la misma calidad; necesita 20 GB o más y una placa de video (GPU).",
    "Built for programming and coding agents; not meant for general chat; needs 30–50 GB of memory.": "Hecha para programar y para agentes de programación; no está pensada para charlar de todo; necesita entre 30 y 50 GB de memoria.",
    "Frontier-class reasoning and agents; text only; needs 64+ GB of memory (a workstation or a pool of devices).": "Razonamiento y agentes al nivel de los mejores modelos; solo texto; necesita 64 GB de memoria o más (una estación de trabajo o varios dispositivos juntos).",
    "A general assistant for chat, code, math and step-by-step tasks, tuned by a community team on Meta's Llama 3.1. It has no fixed persona: it follows the instruction you set. Text only; its base is older than the newest models here.": "Un asistente general para charlar, programar, hacer matemática y tareas paso a paso, ajustado por un equipo de la comunidad sobre Llama 3.1 de Meta. No tiene una personalidad fija: sigue la instrucción que le des. Solo texto; su base es más vieja que los modelos más nuevos de esta lista.",
    "Can think step by step before answering or answer straight away; good at math, code, structured output and using tools. Easy to steer with your own instruction. Text only; needs 10+ GB of memory.": "Puede pensar paso a paso antes de responder o responder directamente; buena para matemática, código, respuestas con formato fijo y uso de herramientas. Fácil de guiar con tu propia instrucción. Solo texto; necesita 10 GB de memoria o más.",
    "A large model with optional step-by-step reasoning, made to be easy to steer. Text only; needs about 24 GB of memory or more.": "Un modelo grande con razonamiento paso a paso opcional, hecho para que sea fácil de guiar. Solo texto; necesita unos 24 GB de memoria o más.",
    "A very large reasoning model, made to be steerable. Text only; needs about 45 GB of memory: a workstation, a Mac with 64 GB or more, or several linked devices.": "Un modelo de razonamiento muy grande, hecho para que se lo pueda guiar. Solo texto; necesita unos 45 GB de memoria: una estación de trabajo, una Mac con 64 GB o más, o varios dispositivos vinculados.",
    "Built to solve math problems step by step (English and Chinese); not meant for general chat or other subjects. Always check the result.": "Hecha para resolver problemas de matemática paso a paso (en inglés y en chino); no está pensada para charlar de todo ni para otros temas. Revisá siempre el resultado.",
    "Trained on English-language legal text (mostly US/UK/EU law): reads, summarises and drafts legal language. Not a lawyer, not trained on Argentine or other local law; check everything with a professional.": "Entrenada con textos legales en inglés (sobre todo derecho de Estados Unidos, el Reino Unido y la Unión Europea): lee, resume y redacta lenguaje legal. No es un abogado ni fue entrenada con derecho argentino ni con otro derecho local; revisá todo con un profesional.",
    "Understands medical text and medical images (X-rays, skin, pathology slides). A research tool, not a doctor and not approved for diagnosis; its own license terms apply.": "Entiende textos médicos e imágenes médicas (radiografías, piel, preparados de patología). Es una herramienta de investigación, no un médico, y no está aprobada para diagnosticar; valen las condiciones de su propia licencia.",
    # ---- linking devices (datas/link) --------------------------------------------------------
    "message too large": "el mensaje es demasiado grande",
    "unexpected message": "llegó un mensaje que no se esperaba",
    "type the address shown on the other device": "escribí la dirección que muestra el otro dispositivo",
    "the address should look like 192.168.1.20:8424": "la dirección tiene que parecerse a 192.168.1.20:8424",
    "the code has {n} letters and digits": "el código tiene {n} letras y números",
    "the other device did not identify itself": "el otro dispositivo no se identificó",
    "that is this same device": "ese es este mismo dispositivo",
    "the other device is not waiting for a code": "el otro dispositivo no está esperando un código",
    "wrong or expired code": "el código es incorrecto o ya venció",
    "the other device could not prove it knows the code — nothing was linked": "el otro dispositivo no pudo demostrar que conoce el código; no se vinculó nada",
    "this device is not linked to that one": "este dispositivo no está vinculado con ese",
    "a phone cannot ask for that": "un teléfono no puede pedir eso",
    "unknown request": "pedido desconocido",
    "that device is not showing a pairing code right now": "ese dispositivo no está mostrando un código en este momento",
    "bad pairing request": "el pedido de vinculación llegó mal formado",
    "wrong code": "código incorrecto",
    "chat sync is off on that device": "en ese dispositivo está apagado «mantener los mismos chats»",
    "sync refused": "el otro dispositivo no aceptó sincronizar los chats",
    "In Forget mode nothing is saved, so there is nothing to sync.": "En modo Olvidar no se guarda nada, así que no hay nada para sincronizar.",
    "the engine's worker could not start on that device": "el ayudante del motor no pudo arrancar en ese dispositivo",
    "the engine's worker did not start in time": "el ayudante del motor no arrancó a tiempo",
    "that device is not sharing its memory": "ese dispositivo no está prestando su memoria",
    "that device is busy running its own AI": "ese dispositivo está ocupado con su propia IA",
    "that device did not allow this one to open its Datas": "ese dispositivo no le dio permiso a este para abrir su Datas",
    "refused": "no fue aceptado",
    "a phone has no Datas to open": "un teléfono no tiene un Datas para abrir",
    "{name} has not allowed this computer to open its Datas. On {name}: Devices → {me} → "
    "switch on “May open Datas on this computer”. If it has no screen, type there: "
    'datas-cli link window "{me}" on': "{name} no le dio permiso a esta computadora para "
    "abrir su Datas. En {name}: Dispositivos → {me} → activá «Puede abrir Datas de esta "
    'computadora». Si no tiene pantalla, escribí ahí: datas-cli link window "{me}" on',
    "not available over the link": "eso no está disponible a través del vínculo",
    "that device is not running an AI of its own": "ese dispositivo no tiene una IA propia en marcha",
    "no AI is running on that device": "no hay ninguna IA en marcha en ese dispositivo",
    "the other device refused": "el otro dispositivo no aceptó",
    "the device at that address is not the one that was linked": "el dispositivo que está en esa dirección no es el que se vinculó",
    "Could not open port {port} on this device ({why}). Another program may be using it.": "No se pudo abrir el puerto {port} en este dispositivo ({why}). Puede que otro programa lo esté usando.",
    "Could not reach {address}. Check that Datas is open on the other device, that it shows the pairing code, and that both are on the same network (or that the address is reachable). ({why})": "No se pudo llegar a {address}. Fijate que Datas esté abierto en el otro dispositivo, que muestre el código y que los dos estén en la misma red (o que se pueda llegar a esa dirección). ({why})",
    "Could not reach that device ({why}). Is it on, and is Datas open on it?": "No se pudo llegar a ese dispositivo ({why}). ¿Está prendido y tiene Datas abierto?",
    # ---- Modbus on a serial cable (datas/things/net.py) ----------------------------------------
    "Could not use {port}: {why}. Is the cable plugged in, and is another program using it?": "No se pudo usar {port}: {why}. ¿Está enchufado el cable? ¿Lo está usando otro programa?",
    "The device on {port} did not answer. Check its unit number ({unit}), the speed ({baud}) and the two wires (A and B).": "El aparato en {port} no respondió. Revisá su número de unidad ({unit}), la velocidad ({baud}) y los dos cables (A y B).",
    "The answer from {port} arrived damaged. Check the speed ({baud}) and the wiring.": "La respuesta de {port} llegó dañada. Revisá la velocidad ({baud}) y el cableado.",
    # ---- offline survival library (datas/survival) ----
    "That document is not in the library.": "Ese documento no está en la biblioteca.",
    "That document has not been checked yet, so it is not offered.": "Ese documento todavía no fue verificado, así que no se ofrece.",
    "The file that arrived from {site} is not the one Datas checked, so it was not kept. The publisher may have changed it; open its page instead: {page}": "El archivo que llegó de {site} no es el que Datas verificó, así que no se guardó. Puede que quien lo publica lo haya cambiado; abrí su página: {page}",
    "Could not download it from {site} ({why}). Check the internet connection, or open its page: {page}": "No se pudo descargar de {site} ({why}). Revisá la conexión a internet, o abrí su página: {page}",
    "That document is not on this device yet.": "Ese documento todavía no está en este dispositivo.",
    "Datas starts when you log in to this Mac.": "Datas arranca cuando iniciás sesión en esta Mac.",
    "Datas starts when you log in to Windows.": "Datas arranca cuando iniciás sesión en Windows.",
}
