package com.lab.monitor.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;

/**
 * mlExecutor 정의.
 *
 * <p>F6 #20: 큐 saturation 관측을 위해 두 가지 메트릭을 Micrometer 에 노출한다.
 * <ul>
 *   <li>{@code rada.ml.executor.rejected} — counter. RejectedExecutionHandler 가
 *       호출될 때마다 1 증가. 핸들러는 기본 AbortPolicy 로 위임하므로 예외 throw
 *       동작은 유지된다 (호출측 코드가 기존 동작에 의존).
 *   <li>{@code rada.ml.executor.queue_size} — gauge. 현재 작업 큐 크기.
 * </ul>
 */
@Configuration
public class AsyncConfig {

    @Bean(name = "mlExecutor")
    public Executor mlExecutor(@Autowired(required = false) MeterRegistry meterRegistry) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mlExecutor-");

        // 기본 AbortPolicy 를 wrap 해서 rejected counter 증가시킴.
        // increment 0번이라도 counter 가 Prometheus 노출되도록 미리 등록.
        final Counter rejectedCounter = meterRegistry != null
                ? Counter.builder("rada.ml.executor.rejected").register(meterRegistry)
                : null;
        RejectedExecutionHandler abort = new ThreadPoolExecutor.AbortPolicy();
        executor.setRejectedExecutionHandler((r, exec) -> {
            if (rejectedCounter != null) {
                rejectedCounter.increment();
            }
            abort.rejectedExecution(r, exec);
        });

        executor.initialize();

        // queue_size gauge — initialize 이후에야 ThreadPoolExecutor 가 존재.
        if (meterRegistry != null) {
            meterRegistry.gauge(
                    "rada.ml.executor.queue_size",
                    executor,
                    e -> e.getThreadPoolExecutor().getQueue().size()
            );
        }
        return executor;
    }
}
