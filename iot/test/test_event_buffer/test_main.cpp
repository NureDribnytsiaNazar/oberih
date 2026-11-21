// ІК-4: буфер подій із наскрізним seq у NVS.
#include <unity.h>

#include "../fake_store.h"
#include "event_buffer.h"

namespace {

constexpr int64_t kServerEpoch = 1763700000;

NodeClock synced_clock(uint32_t at_ms) {
  NodeClock clock;
  clock.sync(kServerEpoch, at_ms);
  return clock;
}

void fill(EventBuffer& buffer, size_t count, bool alarm, const NodeClock& clock) {
  for (size_t i = 0; i < count; ++i) {
    buffer.push(1, alarm ? EventType::kOpened : EventType::kClosed, alarm,
                clock, static_cast<uint32_t>(i));
  }
}

}  // namespace

void setUp() {}
void tearDown() {}

void test_seq_is_sequential_and_order_kept() {
  FakeStore store;
  EventBuffer buffer(store);
  const NodeClock clock = synced_clock(0);
  TEST_ASSERT_EQUAL_UINT64(1, buffer.push(1, EventType::kOpened, true, clock, 0));
  TEST_ASSERT_EQUAL_UINT64(2, buffer.push(3, EventType::kMotion, true, clock, 1500));
  BufferedEvent out[4];
  TEST_ASSERT_EQUAL(2, buffer.peek(out, 4));
  TEST_ASSERT_EQUAL_UINT64(1, out[0].seq);
  TEST_ASSERT_EQUAL_UINT64(2, out[1].seq);
  TEST_ASSERT_EQUAL_INT64(kServerEpoch + 1, out[1].epoch_s);
}

void test_pop_removes_sent_events() {
  FakeStore store;
  EventBuffer buffer(store);
  fill(buffer, 5, false, synced_clock(0));
  buffer.pop(3);
  TEST_ASSERT_EQUAL(2, buffer.size());
  TEST_ASSERT_EQUAL_UINT64(4, buffer.at(0).seq);
}

void test_overflow_drops_oldest_non_alarm() {
  FakeStore store;
  EventBuffer buffer(store);
  const NodeClock clock = synced_clock(0);
  buffer.push(1, EventType::kOpened, true, clock, 0);  // seq 1, тривожна
  fill(buffer, EventBuffer::kCapacity - 1, false, clock);  // seq 2..64
  buffer.push(4, EventType::kTamper, true, clock, 100);  // seq 65
  TEST_ASSERT_EQUAL(EventBuffer::kCapacity, buffer.size());
  TEST_ASSERT_EQUAL(1, buffer.dropped());
  // Тривожна подія seq 1 залишилася, відкинуто найстарішу звичайну (seq 2).
  TEST_ASSERT_EQUAL_UINT64(1, buffer.at(0).seq);
  TEST_ASSERT_EQUAL_UINT64(3, buffer.at(1).seq);
  TEST_ASSERT_EQUAL_UINT64(65, buffer.at(EventBuffer::kCapacity - 1).seq);
}

void test_overflow_with_only_alarms_drops_oldest() {
  FakeStore store;
  EventBuffer buffer(store);
  fill(buffer, EventBuffer::kCapacity + 1, true, synced_clock(0));
  TEST_ASSERT_EQUAL_UINT64(2, buffer.at(0).seq);
}

void test_survives_reboot() {
  FakeStore store;
  {
    EventBuffer before(store);
    fill(before, 3, false, synced_clock(0));
    before.pop(1);
  }
  EventBuffer after(store);  // «перезавантаження»: новий об'єкт, те саме NVS
  after.load();
  TEST_ASSERT_EQUAL(2, after.size());
  TEST_ASSERT_EQUAL_UINT64(2, after.at(0).seq);
  TEST_ASSERT_EQUAL_UINT64(4, after.push(2, EventType::kOpened, false,
                                         synced_clock(0), 10));
}

void test_events_before_clock_sync_get_time_later() {
  FakeStore store;
  EventBuffer buffer(store);
  NodeClock clock;
  buffer.push(1, EventType::kOpened, true, clock, 2000);
  BufferedEvent out[1];
  TEST_ASSERT_EQUAL(0, buffer.peek(out, 1));  // без часу не надсилаємо

  clock.sync(kServerEpoch, 7000);
  buffer.resolve_times(clock);
  TEST_ASSERT_EQUAL(1, buffer.peek(out, 1));
  TEST_ASSERT_EQUAL_INT64(kServerEpoch - 5, out[0].epoch_s);
}

void test_previous_boot_events_get_approximate_time() {
  FakeStore store;
  {
    EventBuffer before(store);
    NodeClock unsynced;
    before.push(1, EventType::kOpened, true, unsynced, 2000);
  }
  EventBuffer after(store);
  after.load();
  after.resolve_times(synced_clock(100));
  TEST_ASSERT_EQUAL_INT64(kServerEpoch, after.at(0).epoch_s);
  TEST_ASSERT_TRUE(after.at(0).flags & EventBuffer::kFlagApproxTime);
}

void test_adopt_server_seq_after_nvs_loss() {
  FakeStore store;
  EventBuffer buffer(store);
  fill(buffer, 2, false, synced_clock(0));  // seq 1, 2 — ще не надіслано
  TEST_ASSERT_FALSE(buffer.adopt_server_seq(2));
  TEST_ASSERT_TRUE(buffer.adopt_server_seq(40));
  TEST_ASSERT_EQUAL_UINT64(41, buffer.at(0).seq);
  TEST_ASSERT_EQUAL_UINT64(42, buffer.last_seq());
}

void test_storage_errors_are_counted() {
  FakeStore store;
  store.fail_writes = true;
  EventBuffer buffer(store);
  fill(buffer, 1, false, synced_clock(0));
  TEST_ASSERT_EQUAL(2, buffer.storage_errors());  // seq і знімок буфера
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_seq_is_sequential_and_order_kept);
  RUN_TEST(test_pop_removes_sent_events);
  RUN_TEST(test_overflow_drops_oldest_non_alarm);
  RUN_TEST(test_overflow_with_only_alarms_drops_oldest);
  RUN_TEST(test_survives_reboot);
  RUN_TEST(test_events_before_clock_sync_get_time_later);
  RUN_TEST(test_previous_boot_events_get_approximate_time);
  RUN_TEST(test_adopt_server_seq_after_nvs_loss);
  RUN_TEST(test_storage_errors_are_counted);
  return UNITY_END();
}
