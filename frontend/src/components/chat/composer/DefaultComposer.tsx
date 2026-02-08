import type { ComponentProps } from "react";
import { Composer } from "./Composer";

type Props = Omit<ComponentProps<typeof Composer.Provider>, "children">;

export const DefaultComposer = ({ onSubmit, disabled }: Props) => {
	return (
		<Composer.Provider onSubmit={onSubmit} disabled={disabled}>
			<Composer.Container>
				<Composer.Textarea />
				<Composer.Toolbar>
					<Composer.ToolbarLeft />
					<Composer.ToolbarRight>
						<Composer.SendButton />
					</Composer.ToolbarRight>
				</Composer.Toolbar>
			</Composer.Container>
		</Composer.Provider>
	);
};
