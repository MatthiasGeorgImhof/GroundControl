/*
 * CC1101Manager.hpp
 */

#pragma once

#include "CC1101.hpp"
#include "RingBuffer.hpp"
#include "usbd_cdc_if.h"
#include <cstring>

enum class RadioState
{
    INIT,
    RX_LISTENING,
    RX_PROCESSING,
    TX_START,
    TX_WAIT_END
};

template <typename RADIO>
class CC1101Manager
{
private:
    RADIO &radio;
    RadioState state = RadioState::INIT;
    RingBuffer<1024> tx_ring;

    // Persistant state for packet nibbling
    bool last_was_zero = false;
    uint8_t packet_len = 0;
    uint8_t packet[1 + 64]; // [0] = len, [1..64] = data

    uint8_t rf_packet_buf[64];
    uint8_t usb_tx_buf[128];
    volatile bool packet_received_flag = false;

    // --- Private Internal Helpers ---

    void force_rx()
    {
        radio.Strobe(RADIO::StrobeCommand::SIDLE);
        radio.Strobe(RADIO::StrobeCommand::SFRX);
        radio.Strobe(RADIO::StrobeCommand::SRX);
        state = RadioState::RX_LISTENING;
    }

    void send_packet(uint8_t len)
    {
        packet[0] = len;
        radio.Strobe(RADIO::StrobeCommand::SIDLE);
        radio.Strobe(RADIO::StrobeCommand::SFTX);
        radio.WriteBurst(RADIO::BurstRegister::TXFIFO, packet, len + 1);
        radio.Strobe(RADIO::StrobeCommand::STX);
        state = RadioState::TX_WAIT_END;
    }

    void handle_rf_read()
    {
        uint8_t rxStatus = radio.ReadStatus(RADIO::StatusRegister::RXBYTES);
        uint8_t bytesInFifo = rxStatus & 0x7F;

        // Check for overflow or too small for CC1101 (Len + Status bytes)
        if (rxStatus & 0x80 || bytesInFifo < 3) return;

        radio.ReadBurst(RADIO::BurstRegister::RXFIFO, rf_packet_buf, bytesInFifo);

        uint8_t pktLen = rf_packet_buf[0];
        bool crc_ok = (rf_packet_buf[pktLen + 2] & 0x80);

        if (crc_ok && pktLen > 0 && pktLen <= 61)
        {
            memcpy(usb_tx_buf, &rf_packet_buf[1], pktLen);
            while (CDC_Transmit_FS(usb_tx_buf, pktLen) == USBD_BUSY);
        }
    }

    void handle_rf_tx()
    {
        if (state == RadioState::TX_WAIT_END) return;

        constexpr uint8_t MAX_DATA_SIZE = 51;
        uint8_t val;

        while (tx_ring.peek(val))
        {
            bool is_zero = (val == 0);

            if (last_was_zero && is_zero)
            {
                if (packet_len > 0)
                {
                    uint8_t to_send = packet_len;
                    packet_len = 0;
                    send_packet(to_send);
                    return;
                }
                tx_ring.pop(val);
                packet_len = 1;
                packet[packet_len] = 0;
                last_was_zero = true;
                continue;
            }

            tx_ring.pop(val);
            packet[++packet_len] = val;
            last_was_zero = is_zero;

            if (packet_len == MAX_DATA_SIZE)
            {
                packet_len = 0;
                send_packet(MAX_DATA_SIZE);
                return;
            }
        }

        if (packet_len > 0)
        {
            uint8_t to_send = packet_len;
            packet_len = 0;
            send_packet(to_send);
        }
        else
        {
            state = RadioState::RX_LISTENING;
        }
    }

public:
    CC1101Manager(RADIO &radio) : radio(radio) {};

    // --- External Callbacks ---

    void handle_usb_data(uint8_t *buf, uint32_t len)
    {
        for (uint32_t i = 0; i < len; i++)
        {
            tx_ring.push(buf[i]);
        }
    }

    void notify_packet_received()
    {
        packet_received_flag = true;
    }

    // --- Main State Machine Loop ---

    void process()
    {
        switch (state)
        {
        case RadioState::INIT:
            radio.Init();
            force_rx();
            break;

        case RadioState::RX_LISTENING:
            // Check hardware overflow
            if ((radio.ReadStatus(RADIO::StatusRegister::MARCSTATE) & 0x1F) == 0x11)
            {
                force_rx();
                return;
            }

            if (packet_received_flag)
            {
                packet_received_flag = false;
                state = RadioState::RX_PROCESSING;
                return;
            }

            if (tx_ring.count() > 0 && HAL_GPIO_ReadPin(GPIOB, GD2_Pin) == GPIO_PIN_RESET)
            {
                state = RadioState::TX_START;
            }
            break;

        case RadioState::RX_PROCESSING:
            handle_rf_read();
            force_rx();
            break;

        case RadioState::TX_START:
            handle_rf_tx();
            break;

        case RadioState::TX_WAIT_END:
            uint8_t marc = radio.ReadStatus(RADIO::StatusRegister::MARCSTATE) & 0x1F;
            if (marc == 0x01) // IDLE
            {
                force_rx();
            }
            else if (marc == 0x16) // TX_UNDERFLOW
            {
                radio.Strobe(RADIO::StrobeCommand::SFTX);
                force_rx();
            }
            break;
        }
    }
};
