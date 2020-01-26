#!/usr/bin/env python3
#
# This file is part of LUNA.
#

import time

from nmigen import Signal, Elaboratable, Module, Cat, ClockDomain, ClockSignal, ResetInserter
from nmigen.lib.cdc import FFSynchronizer

from luna                             import top_level_cli
from luna.apollo                      import ApolloDebugger, ApolloILAFrontend
from luna.gateware.utils.cdc          import synchronize
from luna.gateware.interface.spi      import SPIRegisterInterface, SPIMultiplexer, SPIBus
from luna.gateware.architecture.clock import LunaECP5DomainGenerator
from luna.gateware.interface.psram    import HyperRAMInterface

REGISTER_RAM_REG_ADDR   = 2
REGISTER_RAM_VALUE      = 3

#
# Clock frequencies for each of the domains.
# Can be modified to test at faster or slower frequencies.
#
CLOCK_FREQUENCIES = {
    "fast": 120,
    "sync": 60,
    "ulpi": 60
}


class HyperRAMDiagnostic(Elaboratable):
    """
    Temporary gateware that evaluates HyperRAM skews.
    """


    def elaborate(self, platform):
        m = Module()

        # Generate our clock domains.
        clocking = LunaECP5DomainGenerator(clock_frequencies=CLOCK_FREQUENCIES)
        m.submodules.clocking = clocking

        # Grab a reference to our debug-SPI bus.
        board_spi = synchronize(m, platform.request("debug_spi"))

        # Create a set of registers...
        spi_registers = SPIRegisterInterface(7, 32)
        m.submodules.spi_registers = spi_registers
        m.d.comb += spi_registers.spi.connect(board_spi)


        #
        # HyperRAM test connections.
        #
        ram_bus = platform.request('ram')
        psram = HyperRAMInterface(bus=ram_bus)
        m.submodules += psram

        psram_address_changed = Signal()
        psram_address = spi_registers.add_register(REGISTER_RAM_REG_ADDR, write_strobe=psram_address_changed)

        spi_registers.add_sfr(REGISTER_RAM_VALUE, read=psram.read_data)

        # Hook up our PSRAM.
        m.d.comb += [
            ram_bus.reset          .eq(0),
            psram.single_page      .eq(0),
            psram.perform_write    .eq(0),
            psram.register_space   .eq(1),
            psram.final_word       .eq(1),
            psram.start_transfer   .eq(psram_address_changed),
            psram.address          .eq(psram_address),
        ]

        user_io = Cat(platform.request("user_io", i, dir="o") for i in range(4))
        m.d.comb += [
            user_io[0] .eq(psram.bus.cs),
            user_io[1] .eq(psram.bus.clk),
            user_io[2] .eq(psram.bus.rwds.i),
            user_io[3] .eq(psram.bus.dq.i[7]),
        ]

        # Return our elaborated module.
        return m


if __name__ == "__main__":
    test = top_level_cli(HyperRAMDiagnostic)

    # Create a debug and ILA connection.
    debugger = ApolloDebugger()

    debugger.spi.register_write(REGISTER_RAM_REG_ADDR, 0x0)
    time.sleep(1)
    result = debugger.spi.register_read(REGISTER_RAM_VALUE)
    print(f"read: {result:08x}")
