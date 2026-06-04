-- Schema del database meteo (versionato in git).
-- I dati storici vengono caricati dal seed gitignored db/init/02-data.sql
-- (se presente) DOPO questo file, in ordine alfabetico.
--
-- Questo schema rende il progetto avviabile anche senza il backup:
-- in quel caso il DB parte vuoto ma funzionante e il collector
-- inizia a popolarlo.

SET NAMES utf8mb4;

-- Dati giornalieri (uno o piu' record per giorno, fonte API data-daily)
CREATE TABLE IF NOT EXISTS `daily_rolando` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `observation_date` date NOT NULL,
  `station_code` varchar(50) NOT NULL,
  `station_name` varchar(100) DEFAULT NULL,
  `area` varchar(100) DEFAULT NULL,
  `latitude` float DEFAULT NULL,
  `longitude` float DEFAULT NULL,
  `altitude` int(11) DEFAULT NULL,
  `country` varchar(10) DEFAULT NULL,
  `region_name` varchar(50) DEFAULT NULL,
  `t_min` float DEFAULT NULL,
  `t_med` float DEFAULT NULL,
  `t_max` float DEFAULT NULL,
  `rh_min` int(11) DEFAULT NULL,
  `rh_med` int(11) DEFAULT NULL,
  `rh_max` int(11) DEFAULT NULL,
  `slpres` float DEFAULT NULL,
  `w_max` float DEFAULT NULL,
  `w_med` float DEFAULT NULL,
  `w_dir` varchar(10) DEFAULT NULL,
  `rain` float DEFAULT NULL,
  `rad_med` float DEFAULT NULL,
  `rad_max` float DEFAULT NULL,
  `uv_med` float DEFAULT NULL,
  `uv_max` float DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_daily_date` (`observation_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Dati in tempo reale (rilevazione ogni 15 min, fonte API data-realtime)
CREATE TABLE IF NOT EXISTS `realtime_rolando` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `observation_time_local` datetime DEFAULT NULL,
  `observation_time_utc` datetime DEFAULT NULL,
  `station_code` varchar(50) DEFAULT NULL,
  `place` varchar(100) DEFAULT NULL,
  `area` varchar(100) DEFAULT NULL,
  `latitude` float DEFAULT NULL,
  `longitude` float DEFAULT NULL,
  `altitude` int(11) DEFAULT NULL,
  `country` varchar(10) DEFAULT NULL,
  `region_name` varchar(50) DEFAULT NULL,
  `temperature` float DEFAULT NULL,
  `smlp` float DEFAULT NULL,
  `rh` float DEFAULT NULL,
  `wind_speed` float DEFAULT NULL,
  `wind_direction` varchar(10) DEFAULT NULL,
  `wind_direction_degree` int(11) DEFAULT NULL,
  `wind_gust` float DEFAULT NULL,
  `rain_rate` float DEFAULT NULL,
  `daily_rain` float DEFAULT NULL,
  `dew_point` float DEFAULT NULL,
  `rad` float DEFAULT NULL,
  `uv` float DEFAULT NULL,
  `current_tmin` float DEFAULT NULL,
  `current_tmed` float DEFAULT NULL,
  `current_tmax` float DEFAULT NULL,
  `current_rhmin` float DEFAULT NULL,
  `current_rhmed` float DEFAULT NULL,
  `current_rhmax` float DEFAULT NULL,
  `current_wgustmax` float DEFAULT NULL,
  `current_wspeedmax` float DEFAULT NULL,
  `current_wspeedmed` float DEFAULT NULL,
  `current_uvmed` float DEFAULT NULL,
  `current_uvmax` float DEFAULT NULL,
  `current_radmed` float DEFAULT NULL,
  `current_radmax` float DEFAULT NULL,
  `name` varchar(150) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_realtime_time` (`observation_time_local`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
