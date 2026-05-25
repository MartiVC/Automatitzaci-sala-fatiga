-- ============================================================================
--  oracle_dev_setup.sql
--
--  Crea l'usuari/esquema SALAFATIGA dins del PDB FREEPDB1 d'Oracle Free 23ai
--  per a proves LOCALS al portàtil. NO és per a producció: tant la
--  contrasenya com els permisos estan pensats per a un entorn de
--  desenvolupament sandbox dins d'un contenidor Docker.
--
--  Ús (des de l'amfitrió, amb el contenidor 'oracle-fatiga-dev' arrencat):
--
--    docker exec -i oracle-fatiga-dev sqlplus -S sys/Oracle_Fatiga_Dev_1@FREEPDB1 as sysdba < scripts/oracle_dev_setup.sql
--
--  És IDEMPOTENT: es pot tornar a executar sense por; si l'usuari ja
--  existeix només actualitza la contrasenya i re-aplica els grants.
-- ============================================================================

SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT FAILURE

-- Assegura'ns que estem al PDB FREEPDB1 (no al CDB$ROOT).
ALTER SESSION SET CONTAINER = FREEPDB1;

DECLARE
    v_exists NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_exists FROM dba_users WHERE username = 'SALAFATIGA';

    IF v_exists = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER salafatiga IDENTIFIED BY "Oracle_Fatiga_Dev_1" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS';
        DBMS_OUTPUT.PUT_LINE('Usuari SALAFATIGA creat.');
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER salafatiga IDENTIFIED BY "Oracle_Fatiga_Dev_1"';
        EXECUTE IMMEDIATE 'ALTER USER salafatiga QUOTA UNLIMITED ON USERS';
        DBMS_OUTPUT.PUT_LINE('Usuari SALAFATIGA ja existeix: contrasenya i quota actualitzades.');
    END IF;
END;
/

-- Grants mínims perquè auto_create_schema funcioni i el sync pugui treballar.
GRANT CREATE SESSION  TO salafatiga;
GRANT CREATE TABLE    TO salafatiga;
GRANT CREATE SEQUENCE TO salafatiga;
GRANT CREATE INDEX    TO salafatiga;

-- Sortida.
PROMPT
PROMPT === SALAFATIGA preparat al PDB FREEPDB1 ===
PROMPT Connect string per al PC LAB:  localhost:1521/FREEPDB1
PROMPT Usuari:                        SALAFATIGA
PROMPT Contrasenya:                   Oracle_Fatiga_Dev_1
PROMPT

EXIT
