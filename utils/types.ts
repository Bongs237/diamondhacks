export type Field = {
  key: string;
  label: string;
  placeholder: string | undefined;
  type: string;
  required: boolean;
  validate: (v: any) => string;
};

export type GroupData = {
  group_id: string;
  members: UserData[];
  member_count: number;
  status: string;
  vote_result: string;
};

export type UserData = {
  name: string;
  budget: string;
  available_times: string;
  location: string;
  distance: string;
  likes: string;
  dislikes: string;
};
