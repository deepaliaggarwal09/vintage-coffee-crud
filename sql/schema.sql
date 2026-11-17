-- =====================================================================
--  Vintage Coffee & Beverages Ltd  -  Business Management Database
--  MKT322 Academic Task 2   |   MySQL 8 / MariaDB 10.4+ compatible
--
--  Normalised from the CA 1 dump (vintage_coffee_db):
--    * 3 reference ("dimension") tables : fiscal_years, quarters, companies
--    * 7 data ("fact") tables           : annual_pnl, balance_sheet, cash_flows,
--                                         ratios, quarterly_results,
--                                         shareholding_pattern, peer_comparison
--  Every fact table now points to a dimension table through a FOREIGN KEY,
--  so the same period / company can never be spelled two different ways.
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS peer_comparison;
DROP TABLE IF EXISTS shareholding_pattern;
DROP TABLE IF EXISTS quarterly_results;
DROP TABLE IF EXISTS ratios;
DROP TABLE IF EXISTS cash_flows;
DROP TABLE IF EXISTS balance_sheet;
DROP TABLE IF EXISTS annual_pnl;
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS quarters;
DROP TABLE IF EXISTS fiscal_years;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
--  REFERENCE TABLES
-- ---------------------------------------------------------------------

-- One row per reporting year (FY Mar-2022 ... FY Mar-2026 and the TTM row)
CREATE TABLE fiscal_years (
    year_id         INT           NOT NULL AUTO_INCREMENT,
    fiscal_year_end DATE          NOT NULL,
    year_label      VARCHAR(10)   NOT NULL,
    CONSTRAINT pk_fiscal_years       PRIMARY KEY (year_id),
    CONSTRAINT uq_fy_end             UNIQUE (fiscal_year_end),
    CONSTRAINT uq_fy_label           UNIQUE (year_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One row per calendar quarter-end (30-Jun-2023 ... 30-Jun-2026)
CREATE TABLE quarters (
    quarter_end     DATE          NOT NULL,
    CONSTRAINT pk_quarters PRIMARY KEY (quarter_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Vintage Coffee itself plus every listed peer used for benchmarking
CREATE TABLE companies (
    company_id      INT           NOT NULL AUTO_INCREMENT,
    company_name    VARCHAR(50)   NOT NULL,
    is_vintage      TINYINT(1)    NOT NULL DEFAULT 0,
    CONSTRAINT pk_companies   PRIMARY KEY (company_id),
    CONSTRAINT uq_company_nm  UNIQUE (company_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
--  ANNUAL TABLES  (1 row per fiscal year, year_id is both PK and FK)
-- ---------------------------------------------------------------------

CREATE TABLE annual_pnl (
    year_id              INT           NOT NULL,
    sales_cr             DECIMAL(10,2) DEFAULT NULL,
    expenses_cr          DECIMAL(10,2) DEFAULT NULL,
    operating_profit_cr  DECIMAL(10,2) DEFAULT NULL,
    opm_pct              DECIMAL(5,2)  DEFAULT NULL,
    other_income_cr      DECIMAL(10,2) DEFAULT NULL,
    interest_cr          DECIMAL(10,2) DEFAULT NULL,
    depreciation_cr      DECIMAL(10,2) DEFAULT NULL,
    profit_before_tax_cr DECIMAL(10,2) DEFAULT NULL,
    tax_pct              DECIMAL(5,2)  DEFAULT NULL,
    net_profit_cr        DECIMAL(10,2) DEFAULT NULL,
    eps_rs               DECIMAL(6,2)  DEFAULT NULL,
    dividend_payout_pct  DECIMAL(6,2)  DEFAULT NULL,
    CONSTRAINT pk_annual_pnl PRIMARY KEY (year_id),
    CONSTRAINT fk_pnl_year   FOREIGN KEY (year_id) REFERENCES fiscal_years (year_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE balance_sheet (
    year_id              INT           NOT NULL,
    equity_capital_cr    DECIMAL(10,2) DEFAULT NULL,
    reserves_cr          DECIMAL(10,2) DEFAULT NULL,
    borrowings_cr        DECIMAL(10,2) DEFAULT NULL,
    other_liabilities_cr DECIMAL(10,2) DEFAULT NULL,
    total_liabilities_cr DECIMAL(10,2) DEFAULT NULL,
    fixed_assets_cr      DECIMAL(10,2) DEFAULT NULL,
    cwip_cr              DECIMAL(10,2) DEFAULT NULL,
    investments_cr       DECIMAL(10,2) DEFAULT NULL,
    other_assets_cr      DECIMAL(10,2) DEFAULT NULL,
    total_assets_cr      DECIMAL(10,2) DEFAULT NULL,
    CONSTRAINT pk_balance_sheet PRIMARY KEY (year_id),
    CONSTRAINT fk_bs_year       FOREIGN KEY (year_id) REFERENCES fiscal_years (year_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE cash_flows (
    year_id              INT           NOT NULL,
    cfo_cr               DECIMAL(10,2) DEFAULT NULL,
    cfi_cr               DECIMAL(10,2) DEFAULT NULL,
    cff_cr               DECIMAL(10,2) DEFAULT NULL,
    net_cash_flow_cr     DECIMAL(10,2) DEFAULT NULL,
    free_cash_flow_cr    DECIMAL(10,2) DEFAULT NULL,
    cfo_op_pct           DECIMAL(8,2)  DEFAULT NULL,
    CONSTRAINT pk_cash_flows PRIMARY KEY (year_id),
    CONSTRAINT fk_cf_year    FOREIGN KEY (year_id) REFERENCES fiscal_years (year_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ratios (
    year_id               INT          NOT NULL,
    debtor_days           INT          DEFAULT NULL,
    inventory_days        INT          DEFAULT NULL,
    days_payable          INT          DEFAULT NULL,
    cash_conversion_cycle INT          DEFAULT NULL,
    working_capital_days  INT          DEFAULT NULL,
    roce_pct              DECIMAL(5,2) DEFAULT NULL,
    CONSTRAINT pk_ratios PRIMARY KEY (year_id),
    CONSTRAINT fk_ratio_year FOREIGN KEY (year_id) REFERENCES fiscal_years (year_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
--  QUARTERLY TABLES  (quarter_end is the FK, quarter_id is a surrogate PK)
-- ---------------------------------------------------------------------

CREATE TABLE quarterly_results (
    quarter_id           INT           NOT NULL AUTO_INCREMENT,
    quarter_end          DATE          NOT NULL,
    sales_cr             DECIMAL(10,2) DEFAULT NULL,
    expenses_cr          DECIMAL(10,2) DEFAULT NULL,
    operating_profit_cr  DECIMAL(10,2) DEFAULT NULL,
    opm_pct              DECIMAL(5,2)  DEFAULT NULL,
    other_income_cr      DECIMAL(10,2) DEFAULT NULL,
    interest_cr          DECIMAL(10,2) DEFAULT NULL,
    depreciation_cr      DECIMAL(10,2) DEFAULT NULL,
    profit_before_tax_cr DECIMAL(10,2) DEFAULT NULL,
    tax_pct              DECIMAL(5,2)  DEFAULT NULL,
    net_profit_cr        DECIMAL(10,2) DEFAULT NULL,
    eps_rs               DECIMAL(6,2)  DEFAULT NULL,
    CONSTRAINT pk_quarterly_results PRIMARY KEY (quarter_id),
    CONSTRAINT uq_qr_quarter        UNIQUE (quarter_end),
    CONSTRAINT fk_qr_quarter        FOREIGN KEY (quarter_end) REFERENCES quarters (quarter_end)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE shareholding_pattern (
    quarter_id           INT           NOT NULL AUTO_INCREMENT,
    quarter_end          DATE          NOT NULL,
    promoters_pct        DECIMAL(5,2)  DEFAULT NULL,
    fii_pct              DECIMAL(5,2)  DEFAULT NULL,
    dii_pct              DECIMAL(5,2)  DEFAULT NULL,
    public_pct           DECIMAL(5,2)  DEFAULT NULL,
    num_shareholders     INT           DEFAULT NULL,
    CONSTRAINT pk_shareholding PRIMARY KEY (quarter_id),
    CONSTRAINT uq_sh_quarter   UNIQUE (quarter_end),
    CONSTRAINT fk_sh_quarter   FOREIGN KEY (quarter_end) REFERENCES quarters (quarter_end)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT ck_sh_pcts CHECK (
        (promoters_pct IS NULL OR promoters_pct BETWEEN 0 AND 100) AND
        (fii_pct       IS NULL OR fii_pct       BETWEEN 0 AND 100) AND
        (dii_pct       IS NULL OR dii_pct       BETWEEN 0 AND 100) AND
        (public_pct    IS NULL OR public_pct    BETWEEN 0 AND 100) AND
        (num_shareholders IS NULL OR num_shareholders >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
--  PEER BENCHMARKING
-- ---------------------------------------------------------------------

CREATE TABLE peer_comparison (
    peer_id              INT           NOT NULL AUTO_INCREMENT,
    company_id           INT           NOT NULL,
    cmp_rs               DECIMAL(10,2) DEFAULT NULL,
    pe_ratio             DECIMAL(6,2)  DEFAULT NULL,
    market_cap_cr        DECIMAL(12,2) DEFAULT NULL,
    div_yield_pct        DECIMAL(5,2)  DEFAULT NULL,
    net_profit_qtr_cr    DECIMAL(10,2) DEFAULT NULL,
    qtr_profit_var_pct   DECIMAL(8,2)  DEFAULT NULL,
    sales_qtr_cr         DECIMAL(10,2) DEFAULT NULL,
    qtr_sales_var_pct    DECIMAL(8,2)  DEFAULT NULL,
    roce_pct             DECIMAL(6,2)  DEFAULT NULL,
    CONSTRAINT pk_peer_comparison PRIMARY KEY (peer_id),
    CONSTRAINT uq_peer_company    UNIQUE (company_id),
    CONSTRAINT fk_peer_company    FOREIGN KEY (company_id) REFERENCES companies (company_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_qr_sales ON quarterly_results (sales_cr);
CREATE INDEX idx_peer_roce ON peer_comparison (roce_pct);
