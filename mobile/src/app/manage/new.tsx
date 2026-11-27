import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ScrollView } from "react-native";
import { createResource } from "../../api/endpoints";
import type { ResourceCreate } from "../../api/generated";
import { ResourceForm } from "../../admin/ResourceForm";
import { explain } from "../../lib/errors";
import { s, space } from "../../ui";

export default function NewResource() {
  const router = useRouter();
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: (body: ResourceCreate) => createResource(body),
    onSuccess: (r) => {
      for (const key of ["resources", "resources-all", "admin-resources"])
        qc.invalidateQueries({ queryKey: [key] });
      router.replace(`/manage/${r.resource_id}` as never);
    },
  });
  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { paddingBottom: space.xxl }]}
      keyboardShouldPersistTaps="handled"
    >
      <ResourceForm
        submitLabel="Create resource"
        busy={create.isPending}
        serverError={create.isError ? explain(create.error) : null}
        onSubmit={(body) => create.mutate(body as ResourceCreate)}
      />
    </ScrollView>
  );
}
