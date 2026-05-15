package com.lab.monitor.security;

import com.lab.monitor.entity.PcInfo;
import com.lab.monitor.repository.AgentAuthRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.context.SecurityContextHolder;

import java.time.OffsetDateTime;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ApiKeyAuthFilterTest {

    private AgentAuthRepository repo;
    private ApiKeyHasher hasher;
    private LastSeenTracker tracker;
    private LastSeenUpdater updater;
    private ApiKeyAuthFilter filter;

    @BeforeEach
    void setUp() {
        repo = mock(AgentAuthRepository.class);
        hasher = new ApiKeyHasher("test-pepper");
        tracker = new LastSeenTracker();
        updater = mock(LastSeenUpdater.class);
        filter = new ApiKeyAuthFilter(repo, hasher, tracker, updater);
        SecurityContextHolder.clearContext();
    }

    @Test
    void rejects_missing_api_key() throws Exception {
        HttpServletRequest req = mock(HttpServletRequest.class);
        HttpServletResponse res = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        when(req.getRequestURI()).thenReturn("/api/metrics");
        when(req.getHeader("X-API-Key")).thenReturn(null);

        filter.doFilter(req, res, chain);

        verify(res).sendError(eq(HttpServletResponse.SC_UNAUTHORIZED), anyString());
        verify(chain, never()).doFilter(any(), any());
        verify(repo, never()).findByApiKey(anyString());
        verify(updater, never()).updateAsync(anyString(), any());
    }

    @Test
    void rejects_invalid_api_key() throws Exception {
        HttpServletRequest req = mock(HttpServletRequest.class);
        HttpServletResponse res = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        when(req.getRequestURI()).thenReturn("/api/metrics");
        when(req.getHeader("X-API-Key")).thenReturn("bad");
        when(repo.findByApiKey(hasher.hash("bad"))).thenReturn(Optional.empty());

        filter.doFilter(req, res, chain);

        verify(res).sendError(eq(HttpServletResponse.SC_UNAUTHORIZED), anyString());
        verify(repo, never()).findByApiKey("bad");
        verify(updater, never()).updateAsync(anyString(), any());
    }

    @Test
    void accepts_valid_api_key_and_sets_pcId() throws Exception {
        HttpServletRequest req = mock(HttpServletRequest.class);
        HttpServletResponse res = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        String raw = "good";
        String hashed = hasher.hash(raw);
        PcInfo pc = PcInfo.builder().pcId("pc-1").apiKey(hashed).isActive(true).build();
        when(req.getRequestURI()).thenReturn("/api/metrics");
        when(req.getHeader("X-API-Key")).thenReturn(raw);
        when(repo.findByApiKey(hashed)).thenReturn(Optional.of(pc));

        filter.doFilter(req, res, chain);

        verify(req).setAttribute("pcId", "pc-1");
        verify(chain).doFilter(req, res);
        assertNotNull(SecurityContextHolder.getContext().getAuthentication());
        // first auth in 30s window must trigger last_seen update
        verify(updater, times(1)).updateAsync(eq("pc-1"), any(OffsetDateTime.class));
    }

    @Test
    void last_seen_update_is_throttled_to_one_per_30s_window() throws Exception {
        String raw = "good";
        String hashed = hasher.hash(raw);
        PcInfo pc = PcInfo.builder().pcId("pc-1").apiKey(hashed).isActive(true).build();
        when(repo.findByApiKey(hashed)).thenReturn(Optional.of(pc));

        for (int i = 0; i < 5; i++) {
            HttpServletRequest req = mock(HttpServletRequest.class);
            HttpServletResponse res = mock(HttpServletResponse.class);
            FilterChain chain = mock(FilterChain.class);
            when(req.getRequestURI()).thenReturn("/api/metrics");
            when(req.getHeader("X-API-Key")).thenReturn(raw);
            filter.doFilter(req, res, chain);
        }

        // 5 back-to-back requests collapse to a single async update
        verify(updater, times(1)).updateAsync(eq("pc-1"), any(OffsetDateTime.class));
    }

    @Test
    void skips_non_api_path() throws Exception {
        HttpServletRequest req = mock(HttpServletRequest.class);
        HttpServletResponse res = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        when(req.getRequestURI()).thenReturn("/health");

        filter.doFilter(req, res, chain);

        verify(chain).doFilter(req, res);
        verify(res, never()).sendError(anyInt(), anyString());
        verify(updater, never()).updateAsync(anyString(), any());
    }
}
