-- Tabelas do arquivo bruto (bucket logs-raw). Trocar <ACCOUNT_ID> pelo ID da conta.
-- Sempre filtrar por year/month/day nas consultas: a projeção de partições evita MSCK REPAIR, não o custo do scan.
-- RDS e WAF: cada restart do Alloy regrava o log group (task 2.4), então use SELECT DISTINCT.

CREATE EXTERNAL TABLE IF NOT EXISTS logs_raw_containers (
  env string,
  origin string,
  service string,
  host string,
  log string,
  level string,
  message string,
  logger_name string,
  trace_id string,
  span_id string,
  usuario string
)
PARTITIONED BY (year string, month string, day string, hour string, minute string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
LOCATION 's3://logs-raw-<ACCOUNT_ID>/origin=container-logs/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2026,2036',
  'projection.month.type' = 'integer',
  'projection.month.range' = '1,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '1,31',
  'projection.day.digits' = '2',
  'projection.hour.type' = 'integer',
  'projection.hour.range' = '0,23',
  'projection.hour.digits' = '2',
  'projection.minute.type' = 'integer',
  'projection.minute.range' = '0,59',
  'projection.minute.digits' = '2',
  'storage.location.template' = 's3://logs-raw-<ACCOUNT_ID>/origin=container-logs/year=${year}/month=${month}/day=${day}/hour=${hour}/minute=${minute}'
);

CREATE EXTERNAL TABLE IF NOT EXISTS logs_raw_waf (
  `timestamp` bigint,
  action string,
  terminatingruleid string,
  terminatingruletype string,
  httpsourcename string,
  httprequest struct<clientip:string, country:string, uri:string, args:string, httpmethod:string, requestid:string>
)
PARTITIONED BY (year string, month string, day string, hour string, minute string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
LOCATION 's3://logs-raw-<ACCOUNT_ID>/origin=waf-logs/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2026,2036',
  'projection.month.type' = 'integer',
  'projection.month.range' = '1,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '1,31',
  'projection.day.digits' = '2',
  'projection.hour.type' = 'integer',
  'projection.hour.range' = '0,23',
  'projection.hour.digits' = '2',
  'projection.minute.type' = 'integer',
  'projection.minute.range' = '0,59',
  'projection.minute.digits' = '2',
  'storage.location.template' = 's3://logs-raw-<ACCOUNT_ID>/origin=waf-logs/year=${year}/month=${month}/day=${day}/hour=${hour}/minute=${minute}'
);

-- RDS é texto: uma coluna com a linha inteira
CREATE EXTERNAL TABLE IF NOT EXISTS logs_raw_rds (
  line string
)
PARTITIONED BY (year string, month string, day string, hour string, minute string)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\001'
LOCATION 's3://logs-raw-<ACCOUNT_ID>/origin=rds-logs/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2026,2036',
  'projection.month.type' = 'integer',
  'projection.month.range' = '1,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '1,31',
  'projection.day.digits' = '2',
  'projection.hour.type' = 'integer',
  'projection.hour.range' = '0,23',
  'projection.hour.digits' = '2',
  'projection.minute.type' = 'integer',
  'projection.minute.range' = '0,59',
  'projection.minute.digits' = '2',
  'storage.location.template' = 's3://logs-raw-<ACCOUNT_ID>/origin=rds-logs/year=${year}/month=${month}/day=${day}/hour=${hour}/minute=${minute}'
);
