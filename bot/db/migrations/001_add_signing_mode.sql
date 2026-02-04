-- Migration: Add signing_mode column to MYMTLWALLETBOT table
-- Date: 2026-02-03
-- Description: Adds signing_mode field to support biometric signing

-- Add column with default value 'server'
ALTER TABLE MYMTLWALLETBOT ADD COLUMN signing_mode VARCHAR(10) DEFAULT 'server';

-- Update existing rows to have 'server' as signing_mode
UPDATE MYMTLWALLETBOT SET signing_mode = 'server' WHERE signing_mode IS NULL;
