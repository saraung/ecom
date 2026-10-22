// Only the latest filter request can publish results. Every failure is explicit.
export const createReportLoader = ({ requests, onStart, onResult }) => {
  let generation = 0;
  return async (params) => {
    const current = ++generation;
    onStart();
    const results = await Promise.allSettled(requests.map(({ load }) =>
      Promise.resolve().then(() => load(params))));
    if (current !== generation) return;
    const data = {};
    const failures = [];
    results.forEach((result, index) => {
      const key = requests[index].key;
      if (result.status === 'fulfilled') data[key] = result.value.data;
      else failures.push(key);
    });
    onResult({ data, failures });
  };
};
