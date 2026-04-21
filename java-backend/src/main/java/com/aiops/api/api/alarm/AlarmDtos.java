package com.aiops.api.api.alarm;

import com.aiops.api.domain.alarm.AlarmEntity;

import java.time.OffsetDateTime;

public final class AlarmDtos {

	private AlarmDtos() {}

	public record Summary(Long id, Long skillId, String triggerEvent, String equipmentId,
	                      String lotId, String severity, String status, String title,
	                      OffsetDateTime eventTime, OffsetDateTime createdAt) {}

	public record Detail(Long id, Long skillId, String triggerEvent, String equipmentId,
	                     String lotId, String step, OffsetDateTime eventTime,
	                     String severity, String title, String summary, String status,
	                     String acknowledgedBy, OffsetDateTime acknowledgedAt,
	                     OffsetDateTime resolvedAt, Long executionLogId, Long diagnosticLogId,
	                     OffsetDateTime createdAt) {}

	static Summary summaryOf(AlarmEntity e) {
		return new Summary(e.getId(), e.getSkillId(), e.getTriggerEvent(), e.getEquipmentId(),
				e.getLotId(), e.getSeverity(), e.getStatus(), e.getTitle(),
				e.getEventTime(), e.getCreatedAt());
	}

	static Detail detailOf(AlarmEntity e) {
		return new Detail(e.getId(), e.getSkillId(), e.getTriggerEvent(), e.getEquipmentId(),
				e.getLotId(), e.getStep(), e.getEventTime(), e.getSeverity(),
				e.getTitle(), e.getSummary(), e.getStatus(),
				e.getAcknowledgedBy(), e.getAcknowledgedAt(), e.getResolvedAt(),
				e.getExecutionLogId(), e.getDiagnosticLogId(), e.getCreatedAt());
	}
}
