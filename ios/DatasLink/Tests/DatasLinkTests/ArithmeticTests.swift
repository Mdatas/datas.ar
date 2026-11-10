import XCTest

@testable import DatasLink

/// The phone's arithmetic gives the same answers as the computer's (datas/link/__init__.py):
/// the values below were computed there.
final class ArithmeticTests: XCTestCase {
    func testTheCodeIsCleanedLikeOnTheComputer() {
        XCTAssertEqual(LinkClient.cleanCode("abcd-efgh jklm"), "ABCDEFGHJKLM")
        XCTAssertEqual(LinkClient.cleanCode("  YW6V-YLGD-UG69 "), "YW6VYLGDUG69")
    }

    func testTheKeyAndBothProofsMatchTheComputers() throws {
        let nc = Data(0..<16)
        let ns = Data(16..<32)
        let key = try LinkClient.derive(code: "abcd-efgh jklm", nonces: nc + ns)
        XCTAssertEqual(Crypto.hex(key), "a513fd4350a7920a7862b5ee960a6b7c575e5f921326a036eb736d53c09f5455")
        let me = String(repeating: "11", count: 32)
        let computer = String(repeating: "22", count: 32)
        XCTAssertEqual(
            Crypto.hex(LinkClient.proof(key: key, role: "client", fpSelf: me, fpOther: computer, n1: nc, n2: ns)),
            "32d78d6092c49e9dd1bb5e7b5bd168bd6b9f68df52336b0dcf276759ca0f189c")
        XCTAssertEqual(
            Crypto.hex(LinkClient.proof(key: key, role: "server", fpSelf: computer, fpOther: me, n1: ns, n2: nc)),
            "d67f2fda338f845521b1b7818e0e8bd27e72dbab7a9489f43db8d5659cd36660")
    }

    func testSmallPieces() {
        XCTAssertEqual(Crypto.hex(Crypto.sha256(Data("datas".utf8))),
                       "958d41c80ef75834effc9cbe2e8aee11aede28ada596e876b8261edf53266b40")
        XCTAssertEqual(Crypto.unhex("00ff10Ab"), Data([0, 255, 16, 171]))
        XCTAssertNil(Crypto.unhex("abc"))
        XCTAssertNil(Crypto.unhex("zz"))
        XCTAssertTrue(Crypto.same(Data([1, 2, 3]), Data([1, 2, 3])))
        XCTAssertFalse(Crypto.same(Data([1, 2, 3]), Data([1, 2, 4])))
        XCTAssertFalse(Crypto.same(Data([1, 2, 3]), Data([1, 2])))
        XCTAssertEqual(Crypto.random(32).count, 32)
        XCTAssertNotEqual(Crypto.random(32), Crypto.random(32))
    }

    func testAComputerIsRememberedAndReadBack() {
        let c = Computer(id: String(repeating: "ab", count: 32), name: "Casa \"PC\" ñ", host: "192.168.1.20", port: 8424,
                         secret: String(repeating: "cd", count: 32))
        let text = c.json()
        XCTAssertTrue(text.contains("\"port\":8424"))
        XCTAssertEqual(Computer.from(json: text), c)
        XCTAssertNil(Computer.from(json: "not json"))
        XCTAssertEqual(c.at(host: "10.0.0.2", port: 9000).secret, c.secret)
    }

    func testAnAnswerInPiecesIsPutTogether() {
        let chunked = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
        let (status, body) = DoorCheck.parse(Data(chunked.utf8))
        XCTAssertEqual(status, 200)
        XCTAssertEqual(body, "hello world")
        let plain = "HTTP/1.1 403 Forbidden\r\nContent-Length: 2\r\n\r\nno"
        XCTAssertEqual(DoorCheck.parse(Data(plain.utf8)).0, 403)
        XCTAssertEqual(DoorCheck.parse(Data(plain.utf8)).1, "no")
        XCTAssertEqual(DoorCheck.parse(Data()).0, 0)
    }

    func testNobodyAtTheAddressIsAPlainSentence() {
        // nothing listens on port 9 of this machine
        let c = Computer(id: String(repeating: "ab", count: 32), name: "x", host: "127.0.0.1", port: 9,
                         secret: String(repeating: "cd", count: 32))
        XCTAssertThrowsError(try LinkClient.info(c)) { error in
            XCTAssertTrue(((error as? LinkError)?.message ?? "").contains("Could not reach"))
        }
        XCTAssertThrowsError(try LinkClient.pair(host: "127.0.0.1", port: 9, code: "short", phoneName: "x")) { error in
            XCTAssertTrue(((error as? LinkError)?.message ?? "").contains("12 letters"))
        }
    }
}
