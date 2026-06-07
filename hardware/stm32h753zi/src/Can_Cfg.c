/*
 * Can_Cfg.c — single-controller config for STM32H753ZI FDCAN1.
 *
 * vendor/as `Can.c` reads this through CAN_CONFIG (&Can_Config). It
 * needs: numOfChannels, channelConfigs[], and (optionally)
 * hwIns2ChlMap. Our shape is the simplest possible: one channel
 * routed to hardware instance 0, which our backend
 * (`hardware/stm32h753zi/src/Can_H7.c`) interprets as FDCAN1.
 */

#include "Can.h"
#include "Can_Priv.h"
#include "Can_Cfg.h"

/* Per-channel mutable state (vendor Can.c writes config->context->state
 * during SetControllerMode transitions). */
static Can_ChannelContextType s_can0_context;

/* Single CAN channel: FDCAN1, 500 kbit/s nominal, 87.5% sample point.
 * Matches `examples/com-minimal`'s `Can.json` if it existed (it doesn't
 * for that example, so these numbers are independently chosen to land
 * inside a working FDCAN bit-timing window). */
static const Can_ChannelConfigType s_can0_cfg = {
    .context = &s_can0_context,
#ifndef USE_PORT
    /* No transceiver standby pin to toggle on Nucleo-H753ZI — the
     * board has no on-board CAN transceiver wired by default. Set
     * numOfCtrlPins to zero so vendor Can.c skips the CanAc_SetupPinMode
     * loop entirely. */
    .CtrlPins = NULL,
    .numOfCtrlPins = 0,
    .TrcvPinSTB = 0,
#endif
    .baudrate = 500000u,    /* nominal bit-rate */
    .samplePoint = 88u,     /* 88 % — vendor Can_Priv.h:58 declares this
                             * as uint8_t "unit 1%", so we lose the 0.5 %
                             * resolution here. The actual NBTP register
                             * still gets the precise 87.5 % programmed
                             * inside Can_H7.c::CanAc_Init via TSEG1/2. */
    .hwInstanceId = 0u,     /* hardware index — FDCAN1 in our backend */
    .NormalValueOfTrcvPinSTB = 0u,
};

/* Single-entry channel array. Index 0 = channel 0 = FDCAN1. */
static const Can_ChannelConfigType s_channel_configs[1] = { s_can0_cfg };

/* hwIns2ChlMap[i] gives the channel number for hardware instance i.
 * One controller, one channel: instance 0 → channel 0. */
static const uint8_t s_hw_to_channel[1] = { 0u };

/* The Can_ConfigType vendor/as Can.c dereferences via CAN_CONFIG. */
Can_ConfigType Can_Config = {
    .channelConfigs    = s_channel_configs,
    .hwIns2ChlMap      = s_hw_to_channel,
    .numOfChannels     = CAN_NUM_CHANNELS,
    .sizeOfhwIns2ChlMap = (uint8_t)(sizeof(s_hw_to_channel) /
                                    sizeof(s_hw_to_channel[0])),
};
