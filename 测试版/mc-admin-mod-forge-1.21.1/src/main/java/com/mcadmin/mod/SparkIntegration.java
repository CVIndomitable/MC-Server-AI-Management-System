package com.mcadmin.mod;

import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Spark API 安全封装。
 * 所有直接引用 Spark 类的代码隔离在内部类 SparkAccessor 中，
 * 只有确认 Spark 存在后才会加载该内部类，避免 NoClassDefFoundError。
 */
public class SparkIntegration {
    private static final Logger LOGGER = LoggerFactory.getLogger(SparkIntegration.class);
    private static volatile boolean available;
    private static volatile boolean checked = false;

    /**
     * 延迟检测 Spark 是否可用（Spark 需要在服务器启动后才注册 API）
     */
    public static boolean isAvailable() {
        if (!checked) {
            try {
                Class.forName("me.lucko.spark.api.SparkProvider");
                // 尝试实际获取实例，确认 Spark 已完成初始化
                SparkAccessor.test();
                available = true;
                LOGGER.debug("Spark API detected and available");
            } catch (ClassNotFoundException e) {
                available = false;
                LOGGER.info("Spark mod not installed, Spark integration disabled");
            } catch (Exception e) {
                available = false;
                LOGGER.info("Spark API not ready yet, will retry later");
                return false; // 不标记 checked，允许下次重试
            }
            checked = true;
        }
        return available;
    }

    /**
     * 收集 Spark 提供的详细性能数据，返回 JSON 对象
     * 调用前必须先检查 isAvailable()
     */
    public static JsonObject collectSparkData() {
        if (!isAvailable()) {
            return null;
        }
        try {
            return SparkAccessor.collect();
        } catch (Exception e) {
            LOGGER.warn("Failed to collect Spark data: {}", e.getMessage());
            return null;
        }
    }

    /**
     * 内部类：隔离所有 Spark API 引用，仅在确认 Spark 存在后加载
     */
    private static class SparkAccessor {
        static void test() {
            // 触发 SparkProvider 类加载并获取实例，验证 API 可用
            me.lucko.spark.api.SparkProvider.get();
        }

        static JsonObject collect() {
            me.lucko.spark.api.Spark spark = me.lucko.spark.api.SparkProvider.get();
            JsonObject data = new JsonObject();

            // TPS（多时间窗口）
            collectTps(spark, data);

            // MSPT（含均值和百分位）
            collectMspt(spark, data);

            // CPU 使用率
            collectCpu(spark, data);

            // GC 信息
            collectGc(spark, data);

            return data;
        }

        private static void collectTps(me.lucko.spark.api.Spark spark, JsonObject data) {
            try {
                var tps = spark.tps();
                if (tps == null) return;
                JsonObject tpsObj = new JsonObject();
                tpsObj.addProperty("10s", round(tps.poll(me.lucko.spark.api.statistic.StatisticWindow.TicksPerSecond.SECONDS_10)));
                tpsObj.addProperty("1m", round(tps.poll(me.lucko.spark.api.statistic.StatisticWindow.TicksPerSecond.MINUTES_1)));
                tpsObj.addProperty("5m", round(tps.poll(me.lucko.spark.api.statistic.StatisticWindow.TicksPerSecond.MINUTES_5)));
                tpsObj.addProperty("15m", round(tps.poll(me.lucko.spark.api.statistic.StatisticWindow.TicksPerSecond.MINUTES_15)));
                data.add("tps", tpsObj);
            } catch (Exception e) {
                LOGGER.debug("Spark TPS collection failed: {}", e.getMessage());
            }
        }

        private static void collectMspt(me.lucko.spark.api.Spark spark, JsonObject data) {
            try {
                var mspt = spark.mspt();
                if (mspt == null) return;

                JsonObject msptObj = new JsonObject();
                // 取最近 1 分钟的统计
                var min1 = mspt.poll(me.lucko.spark.api.statistic.StatisticWindow.MillisPerTick.MINUTES_1);
                if (min1 != null) {
                    JsonObject min1Obj = new JsonObject();
                    min1Obj.addProperty("mean", round(min1.mean()));
                    min1Obj.addProperty("p50", round(min1.median()));
                    min1Obj.addProperty("p95", round(min1.percentile95th()));
                    min1Obj.addProperty("max", round(min1.max()));
                    msptObj.add("1m", min1Obj);
                }
                // 最近 10 秒
                var sec10 = mspt.poll(me.lucko.spark.api.statistic.StatisticWindow.MillisPerTick.SECONDS_10);
                if (sec10 != null) {
                    JsonObject sec10Obj = new JsonObject();
                    sec10Obj.addProperty("mean", round(sec10.mean()));
                    sec10Obj.addProperty("p95", round(sec10.percentile95th()));
                    msptObj.add("10s", sec10Obj);
                }
                data.add("mspt", msptObj);
            } catch (Exception e) {
                LOGGER.debug("Spark MSPT collection failed: {}", e.getMessage());
            }
        }

        private static void collectCpu(me.lucko.spark.api.Spark spark, JsonObject data) {
            try {
                JsonObject cpuObj = new JsonObject();
                var process = spark.cpuProcess();
                if (process != null) {
                    cpuObj.addProperty("process_10s", roundPercent(process.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.SECONDS_10)));
                    cpuObj.addProperty("process_1m", roundPercent(process.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.MINUTES_1)));
                    cpuObj.addProperty("process_15m", roundPercent(process.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.MINUTES_15)));
                }
                var system = spark.cpuSystem();
                if (system != null) {
                    cpuObj.addProperty("system_10s", roundPercent(system.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.SECONDS_10)));
                    cpuObj.addProperty("system_1m", roundPercent(system.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.MINUTES_1)));
                    cpuObj.addProperty("system_15m", roundPercent(system.poll(me.lucko.spark.api.statistic.StatisticWindow.CpuUsage.MINUTES_15)));
                }
                data.add("cpu", cpuObj);
            } catch (Exception e) {
                LOGGER.debug("Spark CPU collection failed: {}", e.getMessage());
            }
        }

        private static void collectGc(me.lucko.spark.api.Spark spark, JsonObject data) {
            try {
                var gcMap = spark.gc();
                if (gcMap == null || gcMap.isEmpty()) return;
                JsonObject gcObj = new JsonObject();
                for (var entry : gcMap.entrySet()) {
                    var collector = entry.getValue();
                    JsonObject collectorObj = new JsonObject();
                    collectorObj.addProperty("avg_time_ms", round(collector.avgTime()));
                    collectorObj.addProperty("avg_frequency_ms", collector.avgFrequency());
                    gcObj.add(entry.getKey(), collectorObj);
                }
                data.add("gc", gcObj);
            } catch (Exception e) {
                LOGGER.debug("Spark GC collection failed: {}", e.getMessage());
            }
        }

        private static double round(double value) {
            return Math.round(value * 100.0) / 100.0;
        }

        private static double roundPercent(double value) {
            // Spark CPU 返回 0.0~1.0，转百分比
            return Math.round(value * 1000.0) / 10.0;
        }
    }
}
