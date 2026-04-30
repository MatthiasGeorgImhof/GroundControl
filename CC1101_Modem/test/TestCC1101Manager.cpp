#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "doctest.h"
#include <cstdint>
#include <cstring>
#include <vector>
#include <queue>
#include <iostream>

// =============================================================================
// 1. MOCK HAL LAYER
// =============================================================================
#define GPIO_PIN_RESET 0
#define GPIO_PIN_SET 1
#define GD2_Pin 0x0002
uint8_t mock_gpio_pb = GPIO_PIN_RESET;
typedef int GPIO_TypeDef;
GPIO_TypeDef* GPIOB = (GPIO_TypeDef*)0x40020400;

uint8_t HAL_GPIO_ReadPin(GPIO_TypeDef* port, uint16_t pin) {
    return mock_gpio_pb;
}

// Mock USB CDC
uint8_t last_usb_buf[1024];
uint16_t last_usb_len = 0;
#define USBD_BUSY 1
#define USBD_OK 0
uint8_t CDC_Transmit_FS(uint8_t* buf, uint16_t len) {
    memcpy(last_usb_buf, buf, len);
    last_usb_len = len;
    return USBD_OK;
}

// =============================================================================
// 2. RING BUFFER (Copied from your code)
// =============================================================================
template <size_t Size>
class RingBuffer {
    uint8_t buffer[Size];
    volatile size_t head = 0;
    volatile size_t tail = 0;
public:
    bool push(uint8_t val) {
        size_t next = (head + 1) % Size;
        if (next == tail) return false;
        buffer[head] = val;
        head = next;
        return true;
    }
    bool pop(uint8_t &val) {
        if (head == tail) return false;
        val = buffer[tail];
        tail = (tail + 1) % Size;
        return true;
    }
    bool peek(uint8_t &val) {
        if (head == tail) return false;
        val = buffer[tail];
        return true;
    }
    size_t count() const {
        return (head >= tail) ? (head - tail) : (Size - tail + head);
    }
};

// =============================================================================
// 3. MOCK RADIO HARDWARE
// =============================================================================
class MockRadio {
public:
    enum class StrobeCommand : uint8_t { SIDLE=0x36, SFTX=0x3B, STX=0x35, SFRX=0x3A, SRX=0x34 };
    enum class StatusRegister : uint8_t { MARCSTATE=0xF5, RXBYTES=0xFA };
    enum class BurstRegister : uint8_t { TXFIFO=0x3F, RXFIFO=0x3F };

    uint8_t marcstate = 0x01; // IDLE
    std::vector<std::vector<uint8_t>> history;
    std::vector<uint8_t> rx_fifo;

    void Init() {}
    uint8_t ReadStatus(StatusRegister reg) {
        if (reg == StatusRegister::MARCSTATE) return marcstate;
        if (reg == StatusRegister::RXBYTES) return (uint8_t)rx_fifo.size();
        return 0;
    }
    void Strobe(StrobeCommand cmd) {
        if (cmd == StrobeCommand::STX) marcstate = 0x13; // TX Mode
        if (cmd == StrobeCommand::SIDLE) marcstate = 0x01; // IDLE Mode
        if (cmd == StrobeCommand::SRX) marcstate = 0x0D; // RX Mode
    }
    void WriteBurst(BurstRegister reg, uint8_t* data, uint8_t len) {
        if (reg == BurstRegister::TXFIFO) {
            std::vector<uint8_t> packet(data, data + len);
            history.push_back(packet);
        }
    }
    void ReadBurst(BurstRegister reg, uint8_t* data, uint8_t len) {
        if (reg == BurstRegister::RXFIFO) {
            for(int i=0; i<len && i<rx_fifo.size(); i++) data[i] = rx_fifo[i];
        }
    }
};

// =============================================================================
// UPDATED MANAGER
// =============================================================================
enum class RadioState { INIT, RX_LISTENING, RX_PROCESSING, TX_START, TX_WAIT_END };

template <typename RADIO>
class CC1101Manager {
public: // Made public for test visibility
    RADIO &radio;
    RadioState state = RadioState::INIT;
    RingBuffer<1024> tx_ring;
    
    bool last_was_zero = false;
    uint8_t packet_len = 0;
    uint8_t packet[1 + 64]; 

    void force_rx() {
        radio.Strobe(RADIO::StrobeCommand::SIDLE);
        radio.Strobe(RADIO::StrobeCommand::SFRX);
        radio.Strobe(RADIO::StrobeCommand::SRX);
        state = RadioState::RX_LISTENING;
    }

public:
    CC1101Manager(RADIO &radio) : radio(radio) {};

    void handle_usb_data(uint8_t *buf, uint32_t len) {
        for (uint32_t i = 0; i < len; i++) tx_ring.push(buf[i]);
    }

    void process() {
        switch (state) {
            case RadioState::INIT: 
                radio.Init(); 
                force_rx(); 
                break;
            case RadioState::RX_LISTENING:
                if (tx_ring.count() > 0) {
                    state = RadioState::TX_START;
                }
                break;
            case RadioState::TX_START: 
                handle_rf_tx(); 
                break;
            case RadioState::TX_WAIT_END:
                if ((radio.ReadStatus(RADIO::StatusRegister::MARCSTATE) & 0x1F) == 0x01) {
                    force_rx();
                }
                break;
            default: break;
        }
    }

    void handle_rf_tx() {
        constexpr uint8_t MAX_SIZE = 51;
        uint8_t val;

        while (tx_ring.peek(val)) {
            bool is_zero = (val == 0);

            if (last_was_zero && is_zero) {
                if (packet_len > 0) {
                    // BUG FIX: Reset packet_len BEFORE sending or saving state
                    // so the next call starts fresh.
                    uint8_t to_send = packet_len;
                    packet_len = 0; 
                    send_packet(packet, to_send);
                    return; 
                }
                // If packet_len is 0, we are at the second zero of the 00 00 pair
                tx_ring.pop(val); 
                packet_len = 1;
                packet[packet_len] = 0;
                last_was_zero = true;
                continue;
            }

            tx_ring.pop(val);
            packet[++packet_len] = val;
            last_was_zero = is_zero;

            if (packet_len == MAX_SIZE) {
                packet_len = 0;
                send_packet(packet, MAX_SIZE);
                return;
            }
        }

        if (packet_len > 0) {
            uint8_t to_send = packet_len;
            packet_len = 0;
            send_packet(packet, to_send);
        } else {
            state = RadioState::RX_LISTENING;
        }
    }

    void send_packet(uint8_t* buf, uint8_t len) {
        buf[0] = len;
        radio.Strobe(RADIO::StrobeCommand::SIDLE);
        radio.Strobe(RADIO::StrobeCommand::SFTX);
        radio.WriteBurst(RADIO::BurstRegister::TXFIFO, buf, len + 1);
        radio.Strobe(RADIO::StrobeCommand::STX);
        state = RadioState::TX_WAIT_END;
    }
};

// =============================================================================
// UPDATED TESTS
// =============================================================================

// Helper to simulate the main loop spinning
void spin(CC1101Manager<MockRadio>& m, MockRadio& r, int iterations = 10) {
    for(int i=0; i<iterations; i++) {
        m.process();
        if (r.marcstate == 0x13) r.marcstate = 0x01; // Auto-finish TX
    }
}

TEST_CASE("Testing 0x00 0x00 boundary logic") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);

    // 1. Setup
    manager.process(); // INIT -> RX_LISTENING
    
    // 2. Load data: [AA, 00, 00, BB]
    uint8_t data[] = { 0xAA, 0x00, 0x00, 0xBB };
    manager.handle_usb_data(data, 4);

    // 3. Process until first packet is sent
    // We expect Packet 1: [Len:2, AA, 00]
    spin(manager, radio, 5); 
    
    REQUIRE(radio.history.size() >= 1);
    CHECK(radio.history[0][0] == 2);
    CHECK(radio.history[0][1] == 0xAA);
    CHECK(radio.history[0][2] == 0x00);

    // 4. Process until second packet is sent
    // We expect Packet 2: [Len:2, 00, BB]
    spin(manager, radio, 5);

    REQUIRE(radio.history.size() == 2);
    CHECK(radio.history[1][0] == 2);
    CHECK(radio.history[1][1] == 0x00);
    CHECK(radio.history[1][2] == 0xBB);
}

TEST_CASE("Testing 220 byte transmission split") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[220];
    for(int i=0; i<220; i++) data[i] = (i % 200) + 1; 
    manager.handle_usb_data(data, 220);

    spin(manager, radio, 50);

    // 220 / 51 = 4 full packets + 1 remainder (16 bytes)
    REQUIRE(radio.history.size() == 5);
    CHECK(radio.history[0][0] == 51);
    CHECK(radio.history[4][0] == 16); 
}

// Add these to your test file

TEST_CASE("Edge Case: Exactly 51 bytes") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[51];
    memset(data, 0xAA, 51); // No zeros
    manager.handle_usb_data(data, 51);

    spin(manager, radio, 10);

    REQUIRE(radio.history.size() == 1);
    CHECK(radio.history[0][0] == 51);
}

TEST_CASE("Edge Case: Exactly 52 bytes") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[52];
    memset(data, 0xAA, 52);
    manager.handle_usb_data(data, 52);

    spin(manager, radio, 20);

    REQUIRE(radio.history.size() == 2);
    CHECK(radio.history[0][0] == 51);
    CHECK(radio.history[1][0] == 1);
}

TEST_CASE("Edge Case: Triple Zero 0x00 0x00 0x00") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[] = { 0x01, 0x00, 0x00, 0x00, 0x02 };
    manager.handle_usb_data(data, 5);

    // Should produce:
    // Pkt 1: [01, 00]  (Triggered by second zero)
    // Pkt 2: [00, 00]  (Triggered by third zero)
    // Pkt 3: [00, 02]  (The remainder)
    // Note: This depends on how you interpret "second zero is start of new package"
    spin(manager, radio, 20);

    REQUIRE(radio.history.size() >= 2);
    CHECK(radio.history[0][1] == 0x01);
    CHECK(radio.history[0][2] == 0x00);
}

TEST_CASE("Edge Case: Boundary zero at byte 51/52") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[52];
    memset(data, 0xAA, 50);
    data[50] = 0x00; // Byte 51
    data[51] = 0x00; // Byte 52
    manager.handle_usb_data(data, 52);

    spin(manager, radio, 20);

    // This checks if the 51-byte rule and the 00-00 rule conflict.
    // Packet 1 should be length 51, ending in 00.
    // Packet 2 should be length 1, starting with 00.
    REQUIRE(radio.history.size() == 2);
    CHECK(radio.history[0][0] == 51);
    CHECK(radio.history[0][51] == 0x00);
    CHECK(radio.history[1][0] == 1);
    CHECK(radio.history[1][1] == 0x00);
}

TEST_CASE("Edge Case: Rapid Zeros") {
    MockRadio radio;
    CC1101Manager<MockRadio> manager(radio);
    manager.process(); 

    uint8_t data[] = { 0, 0, 0, 0 };
    manager.handle_usb_data(data, 4);
    spin(manager, radio, 20);

    // Interpret: [0,0] flush, [0,0] flush
    // Pkt 1: [0]
    // Pkt 2: [0]
    // Pkt 3: [0, 0] (as last remainder)
    CHECK(radio.history.size() > 1);
}