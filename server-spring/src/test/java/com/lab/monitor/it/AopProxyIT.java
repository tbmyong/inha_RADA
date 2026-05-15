package com.lab.monitor.it;

import com.lab.monitor.service.MetricsService;
import com.lab.monitor.service.MlForwardService;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Verifies @Async / @Transactional proxying actually wraps the relevant beans.
 *
 * MetricsService.ingest is @Transactional -> must be JDK or CGLIB proxy.
 * MlForwardService.forwardAsync is @Async      -> must be a proxy as well, otherwise
 * async dispatch silently degrades to synchronous in-thread execution.
 */
class AopProxyIT extends AbstractIntegrationTest {

    @Autowired MetricsService metricsService;
    @Autowired MlForwardService mlForwardService;

    @Test
    void metricsService_is_aop_proxy() {
        assertThat(AopUtils.isAopProxy(metricsService))
                .as("MetricsService must be an AOP proxy for @Transactional to apply")
                .isTrue();
    }

    @Test
    void mlForwardService_is_aop_proxy() {
        assertThat(AopUtils.isAopProxy(mlForwardService))
                .as("MlForwardService must be an AOP proxy for @Async to apply")
                .isTrue();
    }
}
