# stm32f4xx watchdog reset

RCC_APB1ENR=0x40023840
WWDG_CR=0x40002C00

kb.m[(RCC_APB1ENR, 4)] |= 0x800
kb.m[(WWDG_CR, 4)] = 0x80

