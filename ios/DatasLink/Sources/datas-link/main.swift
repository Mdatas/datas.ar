import DatasLink
import Foundation

// A tiny command line around the iPhone's link code, for the tests (it is not part of the app):
//   datas-link pair <host> <port> <code> <name>      prints what the phone would remember
//   datas-link info <remembered>                      prints how the computer is
//   datas-link get  <remembered> <path>               a web request through the door
//   datas-link post <remembered> <path> <json>
// It prints the same things as android/link-cli/LinkCli.java, so one test covers both.

func stop(_ message: String) -> Never {
    print("LINK: " + message)
    exit(2)
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else {
    print("usage: datas-link pair <host> <port> <code> <name> | info <remembered> | get <remembered> <path> | post <remembered> <path> <json>")
    exit(64)
}

do {
    switch command {
    case "pair":
        guard arguments.count >= 5 else { stop("pair needs: host port code name") }
        let computer = try LinkClient.pair(host: arguments[1], port: Int(arguments[2]) ?? LinkClient.defaultPort,
                                           code: arguments[3], phoneName: arguments[4], os: "ios")
        print(computer.json())
    case "info":
        guard arguments.count >= 2, let computer = Computer.from(json: arguments[1]) else { stop("that is not a remembered computer") }
        let reply = try LinkClient.info(computer)
        print(LinkClient.json(["name": (reply["name"] as? String) ?? ""]))
    case "get", "post":
        guard arguments.count >= 3, let computer = Computer.from(json: arguments[1]) else { stop("that is not a remembered computer") }
        let door = try Door(computer: computer)
        let (status, text) = DoorCheck.request(port: door.port, method: command == "post" ? "POST" : "GET",
                                               path: arguments[2],
                                               body: command == "post" ? (arguments.count > 3 ? arguments[3] : "{}") : nil)
        door.close()
        print(status)
        print(text)
    default:
        stop("unknown command \(command)")
    }
} catch let error as LinkError {
    stop(error.message)
} catch {
    stop(error.localizedDescription)
}
