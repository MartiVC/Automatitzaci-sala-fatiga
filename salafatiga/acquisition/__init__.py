"""Capa d'adquisició de dades.

Subpaquets:
    - ``variador``: lectura del SPEEDRIVE V2 per Modbus RTU (RS-485). Només lectura.
    - ``plc``:      recepció de dades del PLC per Modbus TCP, i simulador del PLC. [pas 3-4]

Totes les fonts d'adquisició produeixen :class:`~salafatiga.core.datamodel.Reading`
i :class:`~salafatiga.core.datamodel.Event` ja normalitzats al model de dades comú.
"""
