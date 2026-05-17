package com.lab.monitor.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.netty.channel.ChannelOption;
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

@Configuration
public class WebClientConfig {

    @Value("${ml.server.base-url:http://localhost:8000}")
    private String mlBaseUrl;

    @Value("${ml.server.connect-timeout-ms:2000}")
    private int connectTimeoutMs;

    @Value("${ml.server.response-timeout-ms:5000}")
    private int responseTimeoutMs;

    /**
     * WebClient for forwarding to the FastAPI ML server.
     *
     * IMPORTANT: WebClient's default ExchangeStrategies create their own
     * Jackson2JsonEncoder that does NOT inherit Spring Boot's globally
     * configured ObjectMapper. The result is that
     * {@code java.time.OffsetDateTime} gets serialized as a Unix epoch
     * number ({@code 1779034593.38225}), which the ML server's Pydantic
     * model rejects with 422 ("Input should be a valid string").
     *
     * Fix: inject the Spring Boot-configured ObjectMapper (which already
     * has {@code SerializationFeature.WRITE_DATES_AS_TIMESTAMPS=false}
     * and registered {@code JavaTimeModule}) and use it for both the
     * encoder and decoder of this WebClient.
     */
    @Bean(name = "mlWebClient")
    public WebClient mlWebClient(ObjectMapper objectMapper) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, connectTimeoutMs)
                .responseTimeout(Duration.ofMillis(responseTimeoutMs))
                .doOnConnected(conn -> conn
                        .addHandlerLast(new ReadTimeoutHandler(responseTimeoutMs, TimeUnit.MILLISECONDS))
                        .addHandlerLast(new WriteTimeoutHandler(responseTimeoutMs, TimeUnit.MILLISECONDS)));

        return WebClient.builder()
                .baseUrl(mlBaseUrl)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(c -> {
                    c.defaultCodecs().maxInMemorySize(1024 * 1024);
                    c.defaultCodecs().jackson2JsonEncoder(
                            new Jackson2JsonEncoder(objectMapper, MediaType.APPLICATION_JSON));
                    c.defaultCodecs().jackson2JsonDecoder(
                            new Jackson2JsonDecoder(objectMapper, MediaType.APPLICATION_JSON));
                })
                .build();
    }
}
