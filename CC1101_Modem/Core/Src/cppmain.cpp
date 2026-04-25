#include "stm32f4xx_hal.h"
#include "usbd_cdc_if.h"

#include "cppmain.hpp"
#include "CC1101.hpp"
#include "CC1101Manager.hpp"
#include "GpioPin.hpp"

using CC1101_GPIO = GpioPin<GPIOA_BASE, SPI1_CS_Pin>;
using CC1101_T    = CC1101<CC1101_GPIO>;
using CC1101Manager_T = CC1101Manager<CC1101_T>;

CC1101_T cc1101;
CC1101Manager_T radio_manager(cc1101);

int cppmain(void)
{
    HAL_Delay(5000);

    // Warm‑up SPI / CC1101
    cc1101.ReadStatus(CC1101_T::StatusRegister::PARTNUM);
    cc1101.Init();
    cc1101.SetPower(CC1101_T::TXPower::NORMAL);

    while (1)
    {
        radio_manager.process();
    }
}
