# Mapa de registres Modbus — SPEEDRIVE V2

Resum extret del document «Protocolo MODBUS — Equipos SPEEDRIVE V2» (ESPA, v1,
`Protocol Modbus Speedrive_V2.pdf`). Codificat a
`salafatiga/acquisition/variador/registers.py`.

## Comunicació

- Capa física: **RS-485, 9600, N, 8, 1**.
- Mode **RTU**, codificació **big-endian**, registres de **16 bits**.
- Esclau **ID = 1** per defecte (només pot haver-hi un màster i un esclau Modbus).
- Temps de silenci de **3,5 caràcters** (~3,5 ms a 9600) abans i després de cada trama.
- **Només lectura**: l'escriptura per Modbus RTU està anul·lada pel fabricant.
- Trama RTU: `[ID][Funció][Dades][CRC]`. En cas d'error, la resposta porta la
  funció amb el bit 0x80 i un codi: 01 funció invàlida, 02 adreça fora de rang,
  03 dada invàlida, 04 fallada del dispositiu, 05 ACK (en procés), 06 ocupat.

## Funcions de lectura i rangs d'adreces

| Rang (document) | Funció | Tipus | Adreça de trama (0-based) |
|---|---|---|---|
| `@0XXXX` | 01 | Sortides digitals (coils) | `addr = reg − 1` |
| `@1XXXX` | 02 | Entrades digitals (discrete inputs) | `addr = reg − 10001` |
| `@3XXXX` | 04 | Registres d'entrada (paràmetres) | `addr = reg − 30001` |

Exemple del document: registre `30007` → offset `6` (= 30007 − 30001).

## Sortides digitals (`@0XXXX`, funció 01)

| Adreça doc. | Nom | Descripció |
|---|---|---|
| `00001` | `LED_FAULT` | LED vermell superior de la caràtula |
| `00002` | `LED_RUN` | LED verd intermedi de la caràtula |
| `00003` | `LED_LINE` | LED verd inferior de la caràtula |
| `00006` | `RELE_ALARMA` | Sortida lliure de potència per a connexió d'alarma |

(El variador té un màxim de 8 sortides digitals.)

## Entrades digitals (`@1XXXX`, funció 02)

| Adreça doc. | Nom | Descripció |
|---|---|---|
| `10010` | `AUX1` | Entrada auxiliar 1 (p. ex. interruptor de nivell): permet parar/posar en marxa l'equip |
| `10021 + 3·x` | `ALARMA_ADDRx` | L'equip `@x` està en alarma |
| `10022 + 3·x` | `AUTO_ADDRx` | L'equip `@x` en automàtic/manual (consultar abans `BUS_485_ADDx`) |
| `10023 + 3·x` | `BUS_485_ADDx` | L'equip `@x` **NO** comunica pel RS-485 intern del grup |

amb `x = 0..7` (adreça de l'equip dins el grup de pressió). Així:
`ALARMA_ADDR0=10021`, `AUTO_ADDR0=10022`, `BUS_485_ADD0=10023`,
`ALARMA_ADDR1=10024`, …, `ALARMA_ADDR7=10042`, `AUTO_ADDR7=10043`, `BUS_485_ADD7=10044`.

(Les entrades `10001..10009` són les tecles/microruptors de la caràtula
—`KEY_UP`, `KEY_DOWN`, `KEY_LEFT`, `KEY_RIGHT`, `KEY_OK`, `SW1..SW3`…— segons
les pantalles del programa GENIO; no s'usen per a la monitorització.)

## Registres d'entrada (`@3XXXX`, funció 04)

### Globals del variador

| Adreça doc. | Nom | Descripció |
|---|---|---|
| `30007` | `15V` | Tensió de control 15 V |
| `30008` | `TENSION_BUS` / `VBUS` | Tensió del bus de contínua |
| `30049` | `Alarmas` | Codi d'alarma actiu (vegeu taula d'alarmes) |

### Comunicats, indexats per equip `@x` (`x = 0..7`)

| Adreça doc. | Nom | Descripció |
|---|---|---|
| `30013 + 2·x` | `INTENSIDAD_ADDRx` | Intensitat del motor de l'equip `@x` |
| `30014 + 2·x` | `PRESION_ADDRx` | Pressió del transductor de l'equip `@x` |
| `30029 + x` | `HZ_MOTOR_ADDRx` | Freqüència (Hz) del motor de l'equip `@x` |

Per tant: `INTENSIDAD_ADDR0=30013`, `PRESION_ADDR0=30014`, …,
`INTENSIDAD_ADDR7=30027`, `PRESION_ADDR7=30028`, `HZ_MOTOR_ADDR0=30029`, …,
`HZ_MOTOR_ADDR7=30036`.

> ⚠️ El document no especifica el factor d'escala d'aquests registres. De moment
> es registra el valor cru i el catàleg de variables deixa preparats `scale` i
> `offset` per ajustar-ho quan es disposi del factor real.

## Codis d'alarma (valor del registre `30049`)

El valor del registre **no és un camp de bits**: és un **codi enter**. `0` (i
valors no llistats) = sense alarma.

| Codi | Significat |
|---|---|
| 17 | Paràmetres incorrectes (cal actualitzar a paràmetres/versions de fàbrica) |
| 18 | Curtcircuit al motor per consum excessiu |
| 19 | Temperatura excessiva al mòdul IGBT (possible consum excessiu) |
| 20 | UnderVoltage: tensió de control IGBT per sota del mínim |
| 21 | Sobreintensitat: consum excessiu al motor |
| 22 | Temperatura interna excessiva |
| 23 | Sonda: no es detecta lectura del transductor de pressió |
| 24 | Problemes en la regulació de pressió |
| 25 | V20: error de tensió interna |
| 26 | Derivació a terra: detecció de fuita a terra |
| 27 | RFU0 (alarma reservada, no utilitzada) |
| 28 | VBusMax: tensió excessiva al bus de contínua |
| 29 | VBusMin: tensió mínima operativa del bus de contínua |
| 30 | Diferència d'intensitat entre fases del motor excessiva |
| 31 | NMI_IGBT: alarma al mòdul IGBT (sobreconsum, temperatura o tensió incorrecta) |
| 32 | RFU1 (alarma reservada, no utilitzada) |
| 33 | Treball en sec: no es detecta consum al motor (treballant sense aigua) |
| 34 | Temperatura del motor excessiva |
| 35 | Intensitat màxima instantània: sobreconsum al motor |
| 36 | Falta d'aigua (entrada AUX1) |
| 37 | Com485: error de comunicació RS-485 de regulació |
| 38 | FaseEntrada: problema en alguna fase d'entrada (no connectada o desequilibrada) [T2/T4] |
| 39 | Comunicació interna entre microprocessadors CPU i motor |
| 40 | Versions: incoherència entre versió de CPU i versió de motor |
| 41 | Canonada rebentada: pèrdua de pressió per canonada rebentada |

## Equips de la instal·lació (segons el plec)

| Grup | Variador | Tensió | Bomba | Potència |
|---|---|---|---|---|
| 1 | SPEEDRIVE V2 M22 | Monofàsic 230 V | Multi 35 5N | 2 HP |
| 2 | SPEEDRIVE V2 T22 | Trifàsic 400 V | Multi 35 6N | 3 HP |
| 3 | SPEEDRIVE V2 T55 | Trifàsic 400 V | Multi 55 7N | 5,5 HP |
| 4 | SPEEDRIVE V2 T55 | Trifàsic 400 V | VE 121 5N | 7,5 HP |

(El plec preveu 4 grups de pressió de dues bombes amb variador; el `MODBUS
esclau` s'instal·la al Speedrive màster del grup.)
